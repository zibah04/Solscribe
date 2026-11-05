"""Cancellable, bounded local-only Ollama client. No cloud or proxy requests."""
from __future__ import annotations
import http.client
import io
import json
import re
import select
import threading
import time


class Cancelled(Exception):
    pass


class _ResponseReader(io.RawIOBase):
    """Poll cancellation on reads instead of relying on cross-thread shutdown.

    Own a duplicate socket: HTTP/1.0 may detach/close HTTPConnection's handle
    while HTTPResponse still reads its body. No polling timeout poisons a
    buffered socket.makefile reader, and no extra request thread is retained.
    """
    def __init__(self, transport, cancelled, deadline):
        super().__init__()
        self.transport = transport.dup()
        self.transport.setblocking(False)
        self.cancelled, self.deadline = cancelled, deadline

    def readable(self):
        return True

    def readinto(self, buffer):
        if not len(buffer):
            return 0
        while True:
            if self.cancelled.is_set():
                raise Cancelled('Writing cancelled')
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Writing helper exceeded the time limit')
            ready, _, _ = select.select([self.transport], [], [], min(.1, remaining))
            if ready:
                try:
                    return self.transport.recv_into(buffer)
                except BlockingIOError:
                    continue

    def close(self):
        self.transport.close()
        super().close()


class OllamaClient:
    def __init__(self, *, port=11434, timeout=180, context=4096):
        self.port, self.timeout, self.context = port, timeout, context
        self.cancelled = threading.Event()
        self._available = set()
        self._loaded = None

    def cancel(self):
        self.cancelled.set()

    def _request(self, method, path, payload=None, *, streaming=False):
        if self.cancelled.is_set():
            raise Cancelled('Writing cancelled')
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        began = time.monotonic()
        response = None
        cancelled = self.cancelled
        deadline = began + (self.timeout if streaming else min(3, self.timeout))
        class ResponseSocket:
            def __init__(self, transport):
                self.transport = transport
            def makefile(self, mode):
                return io.BufferedReader(_ResponseReader(self.transport, cancelled, deadline))
        connection.response_class = lambda transport, *args, **kwargs: http.client.HTTPResponse(ResponseSocket(transport), *args, **kwargs)
        try:
            connection.connect()
            if self.cancelled.is_set():
                raise Cancelled('Writing cancelled')
            connection.sock.settimeout(min(30 if streaming else 3, self.timeout))
            connection.request(method, path, body=json.dumps(payload).encode() if payload is not None else None,
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            if response.status != 200:
                raise ValueError(f'Writing helper returned HTTP {response.status}')
            if not streaming:
                data = response.read(2 * 1024 * 1024 + 1)
                if len(data) > 2 * 1024 * 1024:
                    raise ValueError('Writing helper response exceeds the supported size')
                return json.loads(data)
            parts, size, finished = [], 0, False
            while True:
                if self.cancelled.is_set():
                    raise Cancelled('Writing cancelled')
                if time.monotonic() - began > self.timeout:
                    raise TimeoutError('Writing helper exceeded the time limit')
                line = response.readline(256 * 1024 + 1)
                if not line:
                    break
                size += len(line)
                if len(line) > 256 * 1024 or size > 2 * 1024 * 1024:
                    raise ValueError('Writing helper response exceeds the supported size')
                item = json.loads(line)
                if not isinstance(item, dict) or item.get('error'):
                    raise ValueError('Writing helper returned an error')
                text = item.get('response', '')
                if not isinstance(text, str):
                    raise ValueError('Invalid writing response')
                parts.append(text)
                if item.get('done'):
                    if item.get('done_reason') == 'length':
                        raise ValueError('Writing helper reached its output limit; no partial report was accepted')
                    if item.get('prompt_eval_count', 0) >= self.context - 256:
                        raise ValueError('Writing helper context is too full for a reliable report')
                    finished = True
                    break
            if not finished:
                raise ValueError('Writing helper response ended before completion')
            return ''.join(parts).strip()
        except Exception as exc:
            if self.cancelled.is_set():
                raise Cancelled('Writing cancelled') from None
            if isinstance(exc, http.client.HTTPException):
                raise ValueError('Writing helper returned an invalid HTTP response') from exc
            raise
        finally:
            if response is not None:
                response.close()
            connection.close()

    def ensure_available(self, model: str):
        if not re.fullmatch(r'[\w./:-]{1,150}', model):
            raise ValueError('Invalid local model name')
        canonical = model if ':' in model else model + ':latest'
        if canonical in self._available:
            return
        response = self._request('GET', '/api/tags')
        if not isinstance(response, dict) or not isinstance(response.get('models'), list):
            raise ValueError('Writing helper model list is invalid')
        names = {item.get('name') for item in response['models'] if isinstance(item, dict)}
        if canonical not in names and model not in names:
            raise ValueError('The selected writing model is not installed')
        self._available.add(canonical)

    def generate(self, model: str, prompt: str, response_json=False) -> str:
        self.ensure_available(model)
        self._loaded = model
        return self._request('POST', '/api/generate', {'model': model, 'prompt': prompt, 'stream': True,
            **({'format': 'json'} if response_json else {}), 'keep_alive': '2m',
            'options': {'temperature': .1, 'num_ctx': self.context, 'num_predict': 1500}}, streaming=True)

    def release(self):
        if self._loaded is None:
            return
        # Best effort, bounded, off the UI thread. Explicitly ask the local server
        # to free its model instead of retaining it alongside the next speech task.
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=2)
        try:
            connection.request('POST', '/api/generate', json.dumps({'model': self._loaded, 'keep_alive': 0}),
                               {'Content-Type': 'application/json'})
            connection.getresponse().read(16384)
        except (OSError, http.client.HTTPException):
            pass
        finally:
            connection.close()

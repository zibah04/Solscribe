"""Asynchronous HTTPS update checks/downloads with bounded buffers and cancellation."""
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest, QNetworkProxyFactory
from . import __version__
from .updates import RELEASES_API, select_update, trusted_url, mark_internet_download


class UpdateClient(QObject):
    checked = Signal(object)
    downloaded = Signal(object)
    failed = Signal(str)
    progress = Signal(int)
    cancelled = Signal()

    def __init__(self, root, current_tag, parent=None):
        super().__init__(parent)
        self.root, self.current_tag = Path(root), current_tag
        QNetworkProxyFactory.setUseSystemConfiguration(True)
        self.manager = QNetworkAccessManager(self)
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(lambda: self._fail('The update connection timed out. Please try again when you are online.'))
        self.drain_timer = QTimer(self)
        self.drain_timer.setSingleShot(True)
        self.drain_timer.timeout.connect(lambda: self._read(self.reply))
        self.reply = None
        self.active = False
        self.file = self.part = None
        self.mode = ''

    def check(self, *, include_previews=True):
        if self.active:
            return
        self.include_previews = include_previews
        self.buffer = bytearray()
        self.mode, self.redirects, self.active = 'check', 0, True
        self._request(RELEASES_API)

    def download(self, update):
        if self.active:
            return
        self.mode, self.redirects, self.active = 'download', 0, True
        self.update = update
        self.received, self.last_progress = 0, -1
        self.digest = hashlib.sha256()
        try:
            folder = self.root / 'updates'
            if not folder.resolve().is_relative_to(self.root.resolve()):
                raise ValueError('The update folder is not available')
            folder.mkdir(exist_ok=True)
            if shutil.disk_usage(folder).free < update.size + 64 * 1024 ** 2:
                raise OSError('Please free some disk space before downloading the update')
            handle, name = tempfile.mkstemp(prefix='.download-', suffix='.part', dir=folder)
            self.part = Path(name)
            self.file = os.fdopen(handle, 'wb')
            self._request(update.url)
        except (OSError, ValueError):
            self._fail('The update download could not start. Please check free disk space and folder access.')

    def _request(self, url):
        try:
            allowed = trusted_url(url, download=self.mode == 'download')
        except ValueError:
            allowed = False
        if not allowed:
            self._fail('The update used an unexpected download address. Nothing was installed.')
            return
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
        request.setRawHeader(b'User-Agent', ('SolScribe/' + __version__).encode('ascii'))
        request.setRawHeader(b'Accept', b'application/vnd.github+json' if self.mode == 'check' else b'application/octet-stream')
        request.setTransferTimeout(15000)
        reply = self.manager.get(request)
        reply.setReadBufferSize(256 * 1024)
        self.reply = reply
        self.response_done = False
        reply.readyRead.connect(lambda: self._read(reply))
        reply.finished.connect(lambda: self._finished(reply))
        self.timer.start(12000 if self.mode == 'check' else 20000)

    def _read(self, reply):
        if reply is not self.reply or not self.active:
            return
        if reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) != 200:
            reply.readAll()
            return
        try:
            budget = 256 * 1024
            while reply.bytesAvailable() and budget > 0:
                data = bytes(reply.read(65536))
                budget -= len(data)
                if self.mode == 'check':
                    self.buffer.extend(data)
                    if len(self.buffer) > 4 * 1024 ** 2:
                        raise ValueError('Update information exceeds the supported size')
                else:
                    self.received += len(data)
                    if self.received > self.update.size:
                        raise ValueError('The update size does not match its release information')
                    self.file.write(data)
                    self.digest.update(data)
                    percent = int(self.received * 100 / self.update.size)
                    if percent != self.last_progress:
                        self.last_progress = percent
                        self.progress.emit(percent)
                    self.timer.start(20000)
            if reply.bytesAvailable():
                self.drain_timer.start(0)
            elif self.response_done:
                self._complete()
        except (OSError, ValueError):
            self._fail('The update download could not be saved or verified. Your current app and meetings are kept.')

    def _finished(self, reply):
        if reply is not self.reply or not self.active:
            return
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        redirect = reply.attribute(QNetworkRequest.RedirectionTargetAttribute)
        if status in (301, 302, 303, 307, 308) and isinstance(redirect, QUrl):
            self.redirects += 1
            if self.redirects > 5:
                self._fail('The update connection redirected too many times. Please try again later.')
                return
            url = reply.url().resolved(redirect).toString()
            self.reply = None
            reply.deleteLater()
            self._request(url)
            return
        if reply.error() != QNetworkReply.NoError or status != 200:
            self._fail('Updates are unavailable right now. Please try again when you are online.')
            return
        self.response_done = True
        self._read(reply)

    def _complete(self):
        try:
            if self.mode == 'check':
                result = select_update(json.loads(self.buffer), self.current_tag, include_previews=self.include_previews)
                self._dispose()
                self.checked.emit(result)
            else:
                if self.received != self.update.size or self.digest.hexdigest() != self.update.sha256:
                    raise ValueError('The update download is incomplete or changed. Please download it again')
                self.file.flush()
                os.fsync(self.file.fileno())
                self.file.close()
                self.file = None
                mark_internet_download(self.part, self.update.url)
                destination = self.part.parent / self.update.filename
                os.replace(self.part, destination)
                self.part = None
                self._dispose()
                self.downloaded.emit(destination)
        except (OSError, ValueError, TypeError):
            self._fail('The update could not be verified. Nothing was installed. Please try downloading it again.')

    def _dispose(self):
        self.timer.stop()
        self.drain_timer.stop()
        self.active = False
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()
            reply.deleteLater()
        if self.file is not None:
            try:
                self.file.close()
            except OSError:
                pass
            self.file = None
        if self.part is not None:
            try:
                self.part.unlink(missing_ok=True)
            except OSError:
                pass
            self.part = None

    def _fail(self, message):
        self._dispose()
        self.failed.emit(message)

    def cancel(self):
        if self.active:
            self._dispose()
            self.cancelled.emit()

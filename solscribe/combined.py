"""Two-source capture with preserved originals and a common software-clock mix."""
from __future__ import annotations
import os
from pathlib import Path
import queue
import threading
import time
import wave
import numpy as np

from .audio import AudioPacket, Decimator48k, deliver_live
from .mixing import TimelineMixer
from .recorder import MicrophoneRecorder, SystemLoopbackRecorder


class CombinedRecorder:
    SAMPLE_RATE = 16000

    def __init__(self, microphone_factory=MicrophoneRecorder, system_factory=SystemLoopbackRecorder):
        self.sources = {'microphone': microphone_factory(), 'system': system_factory()}
        self.path = None
        self.frames = 0
        self.level = 0.0
        self.active = False
        self.live_queue = None
        self.live_dropped = 0
        self.started_at = 0.0
        self._errors = {}
        self._queues = {name: queue.Queue(maxsize=256) for name in self.sources}
        self._stop = threading.Event()
        self.thread = None
        self._offsets = {}
        self._output = None

    @property
    def error(self):
        errors = dict(self._errors)
        for name, source in self.sources.items():
            if source.error:
                errors[name] = source.error
            if source.live_dropped:
                errors[name] = 'Some audio was omitted from the mix. The separate source track is kept.'
        return '; '.join(f'{name}: {message}' for name, message in errors.items()) or None

    @property
    def source_tracks(self):
        return {name: {'path': str(source.path), 'offset': max(0.0, source.started_at - self.started_at)}
                for name, source in self.sources.items() if source.path and Path(source.path).is_file()}

    @property
    def elapsed(self):
        return self.frames / self.SAMPLE_RATE

    def start(self, path: Path, device=None):
        if self.active:
            raise RuntimeError('Combined recording is already running')
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._output = self.path.open('wb', buffering=0)
        self._wave = wave.open(self._output, 'wb')
        self._wave.setnchannels(1)
        self._wave.setsampwidth(2)
        self._wave.setframerate(self.SAMPLE_RATE)
        self.started_at = time.perf_counter()
        devices = device or {}
        for name, source in self.sources.items():
            source.live_queue = self._queues[name]
            filename = self.path.with_name(self.path.stem + f'-{name}.wav')
            try:
                source.start(filename, devices.get(name))
                self._offsets[name] = max(0, source.started_at - self.started_at)
            except Exception as exc:
                self._errors[name] = str(exc)
                source.stop()
        if not any(source.active for source in self.sources.values()):
            self._wave.close()
            self._output.close()
            raise RuntimeError('Neither recording source is available. Check microphone and playback permissions.')
        self.active = True
        self.thread = threading.Thread(target=self._mix, name='SolScribe audio mix', daemon=True)
        self.thread.start()

    def _mix(self):
        mixer = TimelineMixer()
        resamplers = {name: Decimator48k() for name in self.sources}
        pending = {}
        def add(name, packet, end_time=None):
            raw = np.frombuffer(packet.pcm, dtype='<i2').astype(np.float32) / 32768
            if packet.sample_rate == 48000:
                raw = resamplers[name].feed(raw)
            elif packet.sample_rate != 16000:
                raise ValueError('Unsupported source sample rate')
            start = (packet.capture_time - self.started_at if packet.capture_time is not None
                     else self._offsets.get(name, 0) + packet.start_seconds)
            duration = packet.frames / packet.sample_rate
            # Adjacent device-clock timestamps account for small independent
            # clock drift. Large jumps are gaps, never stretched into speech.
            end = start + duration
            if end_time is not None and abs((end_time - start) - duration) < duration * .02:
                end = end_time
            mixer.push(name, raw, max(0, start), max(0, end))
        def write(packets):
            for packet in packets:
                self._wave.writeframes(packet.pcm)
                self.frames += packet.frames
                self.live_dropped += deliver_live(self.live_queue, packet)
            if packets and self.frames // 16000 != (self.frames - sum(packet.frames for packet in packets)) // 16000:
                os.fsync(self._output.fileno())
        try:
            while not self._stop.is_set() or any(not buffer.empty() for buffer in self._queues.values()):
                received = False
                for name, buffer in self._queues.items():
                    for _ in range(32):
                        try:
                            packet = buffer.get_nowait()
                        except queue.Empty:
                            break
                        received = True
                        previous = pending.get(name)
                        if previous is not None:
                            adjacent = packet.start_frame == previous.start_frame + previous.frames
                            end_time = packet.capture_time - self.started_at if adjacent and packet.capture_time is not None else None
                            try:
                                add(name, previous, end_time)
                            except (ValueError, BufferError) as exc:
                                self._errors[name] = str(exc)
                        pending[name] = packet
                self.level = max((source.level for source in self.sources.values()), default=0)
                watermark = time.perf_counter() - self.started_at - .35
                write(mixer.drain(watermark))
                if not any(source.active for source in self.sources.values()) and not self._stop.is_set():
                    self._errors['capture'] = 'Both sources stopped; any captured audio has been kept.'
                    self._stop.set()
                if not received:
                    self._stop.wait(.02)
            for name, packet in pending.items():
                try:
                    add(name, packet)
                except (ValueError, BufferError) as exc:
                    self._errors[name] = str(exc)
            write(mixer.drain(mixer.latest / 16000, final=True))
            if mixer.late_frames:
                self._errors['mix'] = f'{mixer.late_frames / 16000:.2f}s arrived late for the mix. Separate source tracks are kept.'
        except Exception as exc:
            self._errors['mix'] = str(exc)
        finally:
            self._wave.close()
            self._output.close()
            self.active = False

    def stop(self):
        for source in self.sources.values():
            source.stop()
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=20)
            if self.thread.is_alive():
                self._errors['mix'] = 'Mix finalization is still running. Check the saved source tracks.'
        self.active = False
        return self.path

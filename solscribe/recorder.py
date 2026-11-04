"""Microphone capture to 16 kHz mono WAV, using a thread-safe write queue."""
from __future__ import annotations

import queue
import threading
import wave
from pathlib import Path
import numpy as np


class MicrophoneRecorder:
    SAMPLE_RATE = 16000

    def __init__(self):
        self.stream = None
        self.writer = None
        self.queue = None
        self.frames = 0
        self.level = 0.0
        self.error = None
        self.path = None
        self.active = False
        self.live_queue = None
        self.live_dropped = 0

    @staticmethod
    def devices():
        import sounddevice as sd
        return [(i, d['name']) for i, d in enumerate(sd.query_devices()) if d['max_input_channels'] > 0]

    def start(self, path: Path, device=None):
        if self.active:
            raise RuntimeError('Recording is already running')
        import sounddevice as sd
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.queue = queue.Queue(maxsize=1600)
        self.frames = 0
        self.level = 0
        self.error = None
        self.live_dropped = 0
        self.active = True
        self.writer = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer.start()

        def callback(indata, frames, time_info, status):
            if status:
                self.error = str(status)
            raw = indata.copy().tobytes()
            try:
                self.queue.put_nowait((raw, frames))
            except queue.Full:
                self.error = 'Audio recording fell behind; a few samples may have been dropped.'
            # Peak amplitude, normalized to 0..1; UI reads it on its own timer.
            peak = np.max(np.abs(indata.astype(np.int32))) if indata.size else 0
            self.level = min(float(peak) / 32768.0, 1.0)

        try:
            self.stream = sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1,
                                         dtype='int16', blocksize=1024,
                                         device=device, callback=callback)
            self.stream.start()
        except Exception:
            self.active = False
            self.queue.put(None)
            self.writer.join(timeout=5)
            self.stream = None
            raise

    def _writer_loop(self):
        with wave.open(str(self.path), 'wb') as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(self.SAMPLE_RATE)
            while True:
                item = self.queue.get()
                if item is None:
                    break
                raw, frames = item
                out.writeframes(raw)
                if self.live_queue is not None:
                    try:
                        self.live_queue.put_nowait((raw, self.SAMPLE_RATE))
                    except queue.Full:
                        # Never compromise the original recording for slow live captions.
                        self.live_dropped += frames
                self.frames += frames

    def stop(self):
        if not self.active:
            return self.path
        self.active = False
        try:
            if self.stream:
                self.stream.stop()
                self.stream.close()
        finally:
            self.stream = None
            self.queue.put(None)
            self.writer.join(timeout=15)
        return self.path

    @property
    def elapsed(self):
        return self.frames / self.SAMPLE_RATE


class SystemLoopbackRecorder:
    """Experimental Windows WASAPI capture of sound playing through an output device.

    This captures PC playback, not the microphone. Select the normal microphone
    source when recording people in the room.
    """
    SAMPLE_RATE = 48000

    def __init__(self):
        self.path = None
        self.frames = 0
        self.level = 0.0
        self.error = None
        self.active = False
        self.thread = None
        self._stop = threading.Event()
        self._ready = threading.Event()
        self.live_queue = None
        self.live_dropped = 0

    @staticmethod
    def devices():
        import soundcard as sc
        return [(speaker.id, speaker.name) for speaker in sc.all_speakers()]

    def start(self, path: Path, device=None):
        if self.active:
            raise RuntimeError('Already recording computer audio.')
        import soundcard as sc
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.error = None
        self.frames = 0
        self.level = 0
        self.live_dropped = 0
        self._stop.clear()
        self._ready.clear()
        self.active = True

        def capture():
            try:
                speaker = sc.get_speaker(device) if device else sc.default_speaker()
                if speaker is None:
                    raise RuntimeError('No playback device is available for loopback recording.')
                monitor = sc.get_microphone(id=speaker.id, include_loopback=True)
                if monitor is None:
                    raise RuntimeError('Cannot access the selected Windows playback device in loopback mode.')
                with wave.open(str(self.path), 'wb') as out:
                    out.setnchannels(1)
                    out.setsampwidth(2)
                    out.setframerate(self.SAMPLE_RATE)
                    with monitor.recorder(samplerate=self.SAMPLE_RATE, blocksize=4096) as recorder:
                        self._ready.set()
                        while not self._stop.is_set():
                            data = recorder.record(numframes=1024)
                            if data is None or not data.size:
                                continue
                            samples = np.asarray(data, dtype=np.float32)
                            if samples.ndim > 1:
                                samples = samples.mean(axis=1)
                            self.level = min(float(np.max(np.abs(samples))), 1.0)
                            raw = (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()
                            out.writeframes(raw)
                            if self.live_queue is not None:
                                try:
                                    self.live_queue.put_nowait((raw, self.SAMPLE_RATE))
                                except queue.Full:
                                    self.live_dropped += len(samples)
                            self.frames += len(samples)
            except Exception as exc:
                self.error = str(exc)
                self._ready.set()
            finally:
                self.active = False
                self._ready.set()

        self.thread = threading.Thread(target=capture, daemon=True)
        self.thread.start()
        if not self._ready.wait(timeout=8):
            self._stop.set()
            raise RuntimeError('Windows loopback did not initialize. Select a microphone instead.')
        if self.error:
            raise RuntimeError(self.error)

    def stop(self):
        self._stop.set()
        if self.thread:
            self.thread.join(timeout=8)
        self.active = False
        return self.path

    @property
    def elapsed(self):
        return self.frames / self.SAMPLE_RATE

"""Microphone capture to 16 kHz mono WAV, using a thread-safe write queue."""
from __future__ import annotations

import queue
import threading
import wave
from pathlib import Path
import numpy as np
import os
import time
from .audio import AudioPacket, deliver_live


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
        self._wave = None
        self._output = None
        self.started_at = 0.0
        self.captured_frames = 0
        self._adc_origin = None

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
        self.queue = queue.Queue(maxsize=128)
        self.frames = 0
        self.level = 0
        self.error = None
        self.live_dropped = 0
        self.captured_frames = 0
        self._adc_origin = None
        # Open the destination before the audio stream: permission/disk failures
        # must reach the caller rather than silently killing the writer thread.
        self._output = self.path.open('wb', buffering=0)
        try:
            self._wave = wave.open(self._output, 'wb')
            self._wave.setnchannels(1)
            self._wave.setsampwidth(2)
            self._wave.setframerate(self.SAMPLE_RATE)
        except Exception:
            self._output.close()
            raise
        self.active = True
        self.writer = threading.Thread(target=self._writer_loop, daemon=True)
        self.writer.start()

        def callback(indata, frames, time_info, status):
            if not self.active:
                return
            if status:
                self.error = str(status)
            raw = indata.copy().tobytes()
            start = self.captured_frames
            adc_time = getattr(time_info, 'inputBufferAdcTime', 0) if time_info is not None else 0
            if adc_time:
                if self._adc_origin is None:
                    self._adc_origin = adc_time
                start = max(start, round((adc_time - self._adc_origin) * self.SAMPLE_RATE))
            self.captured_frames = start + frames
            current_time = getattr(time_info, 'currentTime', adc_time) if time_info is not None else 0
            captured_at = time.perf_counter() - max(0.0, current_time - adc_time) if adc_time else self.started_at + start / self.SAMPLE_RATE
            packet = AudioPacket(raw, self.SAMPLE_RATE, start, captured_at)
            try:
                self.queue.put_nowait(packet)
            except queue.Full:
                self.error = 'Audio recording fell behind; a few samples may have been dropped.'
            # Peak amplitude, normalized to 0..1; UI reads it on its own timer.
            peak = np.max(np.abs(indata.astype(np.int32))) if indata.size else 0
            self.level = min(float(peak) / 32768.0, 1.0)

        try:
            self.stream = sd.InputStream(samplerate=self.SAMPLE_RATE, channels=1,
                                         dtype='int16', blocksize=1024,
                                         device=device, callback=callback)
            self.started_at = time.perf_counter()
            self.stream.start()
        except Exception:
            self.stop()
            raise

    def _writer_loop(self):
        try:
            with self._wave as out:
                while True:
                    item = self.queue.get()
                    if item is None:
                        break
                    packet = item
                    # Keep the WAV clock aligned even if the capture/write queue
                    # overflows. Missing samples are silence, never collapsed time.
                    gap = max(0, packet.start_frame - self.frames)
                    while gap:
                        count = min(gap, self.SAMPLE_RATE)
                        out.writeframes(b'\0\0' * count)
                        self.frames += count
                        gap -= count
                    out.writeframes(packet.pcm)
                    self.live_dropped += deliver_live(self.live_queue, packet)
                    self.frames = packet.start_frame + packet.frames
                    if self.frames // self.SAMPLE_RATE != (self.frames - packet.frames) // self.SAMPLE_RATE:
                        os.fsync(self._output.fileno())
        except Exception as exc:
            self.error = f'Could not save recording: {exc}'
            self.active = False
        finally:
            if self._output is not None:
                self._output.close()

    def stop(self):
        self.active = False
        if self.stream:
            try:
                self.stream.stop()
            except Exception as exc:
                self.error = self.error or str(exc)
            finally:
                try:
                    self.stream.close()
                except Exception as exc:
                    self.error = self.error or str(exc)
                self.stream = None
        if self.writer and self.writer.is_alive():
            try:
                self.queue.put(None, timeout=2)
            except queue.Full:
                self.error = 'The recording could not finish writing. Please check the saved audio.'
            self.writer.join(timeout=15)
            if self.writer.is_alive():
                self.error = 'The recording is still being saved. Please check available disk space.'
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
        self.started_at = 0.0
        self.frames = 0
        self.level = 0.0
        self.error = None
        self.active = False
        self.thread = None
        self._clock_ratio = 1.0
        self._clock_anchor = None
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
        self._clock_anchor = None
        self._clock_ratio = 1.0
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
                with self.path.open('wb', buffering=0) as output, wave.open(output, 'wb') as out:
                    out.setnchannels(1)
                    out.setsampwidth(2)
                    out.setframerate(self.SAMPLE_RATE)
                    with monitor.recorder(samplerate=self.SAMPLE_RATE, blocksize=4096) as recorder:
                        self.started_at = time.perf_counter()
                        self._ready.set()
                        while not self._stop.is_set():
                            data = recorder.record(numframes=1024)
                            if data is None or not data.size:
                                continue
                            samples = np.asarray(data, dtype=np.float32)
                            if samples.ndim > 1:
                                samples = samples.mean(axis=1)
                            self.level = min(float(np.max(np.abs(samples))), 1.0)
                            observed_end = time.perf_counter()
                            if self._clock_anchor is None:
                                self.started_at = observed_end - len(samples) / self.SAMPLE_RATE
                                self._clock_anchor = (observed_end, self.frames + len(samples))
                            nominal_elapsed = (self.frames + len(samples) - self._clock_anchor[1]) / self.SAMPLE_RATE
                            if nominal_elapsed >= 5:
                                observed_ratio = (observed_end - self._clock_anchor[0]) / nominal_elapsed
                                self._clock_ratio = .99 * self._clock_ratio + .01 * min(1.002, max(.998, observed_ratio))
                            raw = (np.clip(samples, -1, 1) * 32767).astype(np.int16).tobytes()
                            out.writeframes(raw)
                            self.live_dropped += deliver_live(self.live_queue, AudioPacket(raw, self.SAMPLE_RATE, self.frames, self.started_at + self.frames / self.SAMPLE_RATE * self._clock_ratio))
                            self.frames += len(samples)
                            if self.frames // self.SAMPLE_RATE != (self.frames - len(samples)) // self.SAMPLE_RATE:
                                os.fsync(output.fileno())
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

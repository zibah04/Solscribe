"""Streaming, on-device caption engine for SolScribe.

Audio capture *never* waits for speech recognition. Captured PCM is sent to a
separate bounded queue, and Whisper runs in a dedicated Qt worker thread.
During live capture these are near-live caption chunks, not a word-for-word
simultaneous streaming decoder. Full post-recording transcription is the
recommended way to polish segment boundaries and completeness.
"""
from __future__ import annotations

import queue
import threading

import numpy as np
from PySide6.QtCore import QThread, Signal
from .audio import AudioPacket
from .captioning import CaptionEngine
from .speech_resources import cpu_threads, release_model


class LiveTranscriptionWorker(QThread):
    """CPU-only streaming captions from PCM messages from the recorder writer.

    An explicit stop() allows the worker to finish queued audio and its final
    partial chunk before emitting QThread.finished.
    """
    status = Signal(str)
    segment_batch = Signal(object)
    failed = Signal(str)
    
    def __init__(self, audio_queue, model_name, language, models_folder, parent=None,
                 chunk_seconds=2.0, model_factory=None):
        super().__init__(parent)
        self.audio_queue = audio_queue
        self.model_name = model_name
        self.language = None if language == 'auto' else language
        self.models_folder = str(models_folder)
        self.chunk_seconds = chunk_seconds
        self._stop_event = threading.Event()
        self._model_factory = model_factory
        self.processed_seconds = 0.0
        self.dropped_audio = 0.0
        self.metrics = {}
        self._cancel = threading.Event()

    def stop(self):
        self._stop_event.set()

    def cancel(self):
        self._cancel.set()
        self._stop_event.set()

    def run(self):
        model = None
        try:
            if self._cancel.is_set():
                return
            if self._model_factory is None:
                from faster_whisper import WhisperModel
                factory = WhisperModel
            else:
                factory = self._model_factory
            self.status.emit('Getting ready to listen · first use needs a download. Your recording is safe.')
            model = factory(self.model_name, device='cpu', compute_type='int8',
                            download_root=self.models_folder, cpu_threads=cpu_threads())
            if self._cancel.is_set():
                return
            engine = CaptionEngine(model, self.language, chunk_seconds=self.chunk_seconds, notify=self.status.emit)
            self.status.emit('Listening · speak naturally; your words will appear below')
            legacy_frame = 0
            while not self._cancel.is_set():
                try:
                    packet = self.audio_queue.get(timeout=.1)
                except queue.Empty:
                    if self._stop_event.is_set():
                        break
                    continue
                if not isinstance(packet, AudioPacket):
                    raw, rate = packet
                    packet = AudioPacket(raw, rate, legacy_frame)
                    legacy_frame += packet.frames
                parts = engine.accept(packet)
                self.processed_seconds = engine.processed_seconds
                self.dropped_audio = engine.skipped_seconds
                if parts:
                    self.segment_batch.emit(parts)
            if not self._cancel.is_set():
                tail = engine.finish()
                self.processed_seconds = engine.processed_seconds
                if tail:
                    self.segment_batch.emit(tail)
                self.status.emit('Your words are saved · you can review and improve the transcript')
            times = list(engine.processing_times)
            self.metrics = {'processed_until_s': self.processed_seconds, 'skipped_s': engine.skipped_seconds,
                            'window_count_sampled': len(times),
                            'mean_processing_s': float(np.mean(times)) if times else 0,
                            'max_processing_s': max(times, default=0)}
        except Exception as exc:
            if not self._cancel.is_set():
                self.failed.emit(f'{type(exc).__name__}: {exc}')
        finally:
            if model is not None:
                release_model(model)

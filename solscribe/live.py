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
from .pcm import PCMChunker


class LiveTranscriptionWorker(QThread):
    """CPU-only streaming captions from PCM messages from the recorder writer.

    An explicit stop() allows the worker to finish queued audio and its final
    partial chunk before emitting QThread.finished.
    """
    status = Signal(str)
    segment_batch = Signal(object)
    failed = Signal(str)
    
    def __init__(self, audio_queue, model_name, language, models_folder, parent=None,
                 chunk_seconds=6.0, model_factory=None):
        super().__init__(parent)
        self.audio_queue = audio_queue
        self.model_name = model_name
        self.language = None if language == 'auto' else language
        self.models_folder = str(models_folder)
        self.chunk_seconds = chunk_seconds
        self._stop_event = threading.Event()
        self._model_factory = model_factory
        self.processed_seconds = 0.0
        self.dropped_audio = 0

    def stop(self):
        self._stop_event.set()

    @staticmethod
    def _has_speech(audio):
        # Energy gate rejects near-silence which can trigger Whisper hallucination.
        return bool(audio.size and np.sqrt(np.mean(audio * audio)) >= 0.003)

    def _infer(self, model, piece):
        offset, audio = piece
        self.processed_seconds = offset + len(audio) / PCMChunker.OUTPUT_RATE
        if not self._has_speech(audio):
            return
        segments_iter, _ = model.transcribe(
            audio, language=self.language, beam_size=1, best_of=1,
            vad_filter=False, condition_on_previous_text=False,
            temperature=0.0, no_speech_threshold=0.5,
        )
        segments = []
        for part in segments_iter:
            content = (part.text or '').strip()
            if content:
                start = max(0.0, float(part.start))
                end = max(start, float(part.end))
                segments.append({'start': round(offset + start, 2),
                                 'end': round(offset + end, 2),
                                 'speaker': 'Speaker', 'text': content})
        if segments:
            self.segment_batch.emit(segments)

    def run(self):
        try:
            if self._model_factory is None:
                from faster_whisper import WhisperModel
                factory = WhisperModel
            else:
                factory = self._model_factory
            self.status.emit(f'Loading live speech model ({self.model_name})…')
            model = factory(self.model_name, device='cpu', compute_type='int8',
                            download_root=self.models_folder, cpu_threads=4)
            self.status.emit('Live captions enabled · updates every few seconds')
            chunker = PCMChunker(self.chunk_seconds)
            while True:
                try:
                    item = self.audio_queue.get(timeout=0.15)
                except queue.Empty:
                    if self._stop_event.is_set():
                        break
                    continue
                raw, sample_rate = item
                for piece in chunker.feed(raw, sample_rate):
                    self._infer(model, piece)
            piece = chunker.flush()
            if piece:
                self._infer(model, piece)
            self.status.emit('Live captions complete · use Transcribe for a polished final transcript')
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')

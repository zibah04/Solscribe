"""Background CPU-optimized Whisper transcription worker."""
from __future__ import annotations

import threading
from pathlib import Path
from PySide6.QtCore import QThread, Signal


class TranscriptionWorker(QThread):
    status = Signal(str)
    progress = Signal(int)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, audio_path, model_name, language, models_folder, parent=None):
        super().__init__(parent)
        self.audio_path = str(audio_path)
        self.model_name = model_name
        self.language = None if language == 'auto' else language
        self.models_folder = str(models_folder)
        self._cancel = threading.Event()

    def cancel(self):
        self._cancel.set()

    def run(self):
        try:
            if not Path(self.audio_path).is_file():
                raise FileNotFoundError('Audio file is missing. Please import it again.')
            self.status.emit('Getting ready to read your recording · first use needs a download…')
            from faster_whisper import WhisperModel
            model = WhisperModel(self.model_name, device='cpu', compute_type='int8',
                                 download_root=self.models_folder, cpu_threads=4)
            if self._cancel.is_set():
                return
            self.status.emit('Turning your recording into text…')
            iterator, info = model.transcribe(self.audio_path, language=self.language,
                                              beam_size=5, vad_filter=True,
                                              condition_on_previous_text=False)
            segments = []
            duration = float(info.duration or 0)
            for segment in iterator:
                if self._cancel.is_set():
                    self.status.emit('Transcription cancelled')
                    return
                text = segment.text.strip()
                if text:
                    segments.append({'start': round(segment.start, 2),
                                     'end': round(segment.end, 2),
                                     'speaker': 'Speaker', 'text': text})
                if duration > 0:
                    self.progress.emit(min(99, int(segment.end / duration * 100)))
            self.progress.emit(100)
            self.result.emit({'segments': segments, 'duration': duration,
                              'language': info.language or '', 'model': self.model_name})
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')

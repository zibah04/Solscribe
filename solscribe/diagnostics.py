"""Opt-in release speech-engine verification. Never records a physical device."""
import json
import queue
import time
import wave
from pathlib import Path
from PySide6.QtCore import QCoreApplication
from .audio import AudioPacket
from .live import LiveTranscriptionWorker


def speech_smoke(filename, output, models):
    app = QCoreApplication.instance() or QCoreApplication([])
    audio_queue = queue.Queue()
    with wave.open(str(filename), 'rb') as audio:
        if (audio.getframerate(), audio.getnchannels(), audio.getsampwidth()) != (16000, 1, 2):
            raise ValueError('Speech smoke audio must be 16kHz mono PCM16 WAV')
        duration = audio.getnframes() / 16000
        position = 0
        while raw := audio.readframes(1024):
            packet = AudioPacket(raw, 16000, position)
            audio_queue.put(packet)
            position += packet.frames
    worker = LiveTranscriptionWorker(audio_queue, 'tiny', 'en', Path(models))
    batches, errors = [], []
    metrics = {'scope': 'Prerecorded synthetic speech queued immediately; not microphone or real-time caption latency.',
               'model': 'tiny', 'compute_type': 'int8', 'device': 'cpu', 'audio_s': duration}
    began = time.perf_counter()
    def status(text):
        if text.startswith('Listening') and 'ready_s' not in metrics:
            metrics['ready_s'] = time.perf_counter() - began
    def received(parts):
        metrics.setdefault('first_caption_s_including_model_start', time.perf_counter() - began)
        batches.extend(parts)
    worker.segment_batch.connect(received)
    worker.failed.connect(errors.append)
    worker.status.connect(status)
    worker.start()
    try:
        deadline = time.monotonic() + 180
        while not batches and not errors and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        if errors or not batches or not worker.isRunning():
            raise RuntimeError('Real speech did not produce captions before Stop: ' + '; '.join(errors))
    finally:
        worker.stop()
        deadline = time.monotonic() + 120
        while worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.01)
        if not worker.wait(1000):
            raise RuntimeError('Speech smoke worker did not finish within the verification timeout')
        app.processEvents()
        metrics.update(worker.metrics)
        metrics['total_s_including_model_start'] = time.perf_counter() - began
        metrics['decode_and_drain_s'] = metrics['total_s_including_model_start'] - metrics.get('ready_s', 0)
        metrics['decode_and_drain_real_time_factor'] = metrics['decode_and_drain_s'] / max(.001, duration)
        metrics['segments'] = len(batches)
        text = ' '.join(part['text'] for part in batches).lower()
        metrics['recognized_expected_keywords'] = 'meeting' in text and 'report' in text
        Path(output).write_text(json.dumps(metrics, indent=2), encoding='utf-8')
    if errors or not metrics['recognized_expected_keywords']:
        raise RuntimeError('Speech smoke failed keyword or worker-error checks')
    return metrics

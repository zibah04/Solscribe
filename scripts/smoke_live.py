"""Recognize a real 16 kHz WAV using the same live worker as the desktop app."""
import queue
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QCoreApplication
from solscribe.live import LiveTranscriptionWorker


def main():
    app = QCoreApplication([])
    audio_queue = queue.Queue()
    with wave.open(sys.argv[1], 'rb') as audio:
        assert audio.getframerate() == 16000 and audio.getnchannels() == 1 and audio.getsampwidth() == 2
        while raw := audio.readframes(1024):
            audio_queue.put((raw, 16000))
    worker = LiveTranscriptionWorker(audio_queue, 'tiny', 'en', Path('.smoke-models'))
    batches, errors = [], []
    worker.segment_batch.connect(batches.extend)
    worker.failed.connect(errors.append)
    worker.status.connect(print)
    worker.start()
    try:
        deadline = time.monotonic() + 180
        while not batches and not errors and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
        assert not errors, errors
        assert batches, 'No real speech recognized before stopping the live worker'
        assert worker.isRunning(), 'Worker should remain live until explicitly stopped'
        print('PASS: real caption received before Stop:', batches[0]['text'])
    finally:
        worker.stop()
        deadline = time.monotonic() + 90
        while worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
        assert worker.wait(1000), 'Live worker did not finish'
        app.processEvents()
    assert not errors, errors
    text = ' '.join(part['text'] for part in batches)
    print('Recognized:', text)
    assert 'meeting' in text.lower() and 'report' in text.lower(), text


if __name__ == '__main__':
    main()

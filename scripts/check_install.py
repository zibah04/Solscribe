"""Seed and verify existing meeting data during the Windows installer smoke test."""
import os
import sqlite3
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
root = Path(os.environ['LOCALAPPDATA']) / 'SolScribe'
if sys.argv[1] == 'seed':
    from solscribe.storage import Store
    store = Store(root)
    audio = store.recordings / 'existing-meeting.wav'
    with wave.open(str(audio), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\0\0' * 1600)
    sid = store.create('Existing meeting', str(audio))
    store.update(sid, summary='Notes that must survive installation and removal.')
    (root / 'seed-id.txt').write_text(sid)
else:
    assert sys.argv[1] == 'verify'
    database = root / 'solscribe.db'
    assert database.is_file(), 'Existing database was removed'
    with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
        row = connection.execute('SELECT title, summary, audio_path FROM sessions WHERE id = ?',
                                 ((root / 'seed-id.txt').read_text(),)).fetchone()
    assert row and row[:2] == ('Existing meeting', 'Notes that must survive installation and removal.'), row
    with wave.open(row[2], 'rb') as recording:
        assert recording.getnframes() == 1600
    print('PASS: existing meeting, notes and recording were preserved')

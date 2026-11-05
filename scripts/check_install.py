"""Exercise migration of a real pre-0.4 schema across install/remove/reinstall."""
import json
import os
import sqlite3
import sys
import uuid
import wave
import traceback
from pathlib import Path

def main():
    root = Path(os.environ['LOCALAPPDATA']) / 'SolScribe'
    if sys.argv[1] == 'seed':
        root.mkdir(parents=True, exist_ok=True)
        audio = root / 'recordings' / 'existing-meeting.wav'
        audio.parent.mkdir(exist_ok=True)
        with wave.open(str(audio), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            output.writeframes(b'\0\0' * 1600)
        sid = uuid.uuid4().hex
        with sqlite3.connect(root / 'solscribe.db') as connection:
            connection.execute('''CREATE TABLE sessions (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                title TEXT NOT NULL, audio_path TEXT DEFAULT '', duration REAL DEFAULT 0,
                language TEXT DEFAULT '', model TEXT DEFAULT '', segments TEXT DEFAULT '[]',
                meeting_date TEXT DEFAULT '', attendees TEXT DEFAULT '', location TEXT DEFAULT '',
                chair TEXT DEFAULT '', agenda TEXT DEFAULT '', summary TEXT DEFAULT '',
                minutes TEXT DEFAULT '', memo TEXT DEFAULT '', actions TEXT DEFAULT '', notes TEXT DEFAULT '')''')
            connection.execute('INSERT INTO sessions(id,created_at,updated_at,title,audio_path,summary,segments) VALUES(?,?,?,?,?,?,?)',
                               (sid, '2026-01-01', '2026-01-01', 'Existing meeting', str(audio),
                                'Notes that must survive installation and removal.',
                                json.dumps([{'start': 0, 'end': .1, 'speaker': 'Alice', 'text': 'Keep my words.'}])))
        (root / 'seed-id.txt').write_text(sid)
    else:
        assert sys.argv[1] == 'verify'
        database = root / 'solscribe.db'
        assert database.is_file(), 'Existing database was removed'
        with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
            row = connection.execute('SELECT title, summary, audio_path, segments FROM sessions WHERE id = ?',
                                     ((root / 'seed-id.txt').read_text(),)).fetchone()
            assert connection.execute('PRAGMA user_version').fetchone()[0] == 5
            assert connection.execute('SELECT owned FROM recordings').fetchone()[0] == 0, 'Legacy media was implicitly claimed'
            lectures = connection.execute("SELECT study_notes, study_items, study_source_hash FROM sessions WHERE session_type='lecture' AND study_notes != ''").fetchall()
            assert lectures, 'Lecture study data was not retained'
            for notes, items, fingerprint in lectures:
                assert 'Definitions' in notes and fingerprint
                cards = [item for item in json.loads(items) if item['kind'] == 'revision']
                assert cards and all(card['answer'] and card['evidence'] for card in cards)
        assert row and row[:2] == ('Existing meeting', 'Notes that must survive installation and removal.'), row
        assert json.loads(row[3])[0]['speaker'] == 'Alice'
        with wave.open(row[2], 'rb') as recording:
            assert recording.getnframes() == 1600
        print('PASS: existing meeting, speaker name, audio and lecture notes/cards/evidence survived')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        details = traceback.format_exc()
        escaped = details[-4500:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::error title=Existing-data validation::' + escaped)
        raise

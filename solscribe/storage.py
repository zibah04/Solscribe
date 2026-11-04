"""Local SQLite session storage. No cloud synchronization or telemetry."""
from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

FIELDS = {
    'title', 'audio_path', 'duration', 'language', 'model', 'segments',
    'meeting_date', 'attendees', 'location', 'chair', 'agenda',
    'summary', 'minutes', 'memo', 'actions', 'notes', 'updated_at',
}


def data_dir() -> Path:
    if os.name == 'nt':
        root = Path(os.getenv('LOCALAPPDATA') or (Path.home() / 'AppData' / 'Local'))
    else:
        root = Path(os.getenv('XDG_DATA_HOME') or Path.home() / '.local' / 'share')
    path = root / 'SolScribe'
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec='seconds')


class Store:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root else data_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.recordings = self.root / 'recordings'
        self.recordings.mkdir(exist_ok=True)
        self.models = self.root / 'models'
        self.models.mkdir(exist_ok=True)
        self.database = self.root / 'solscribe.db'
        with self.connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                title TEXT NOT NULL, audio_path TEXT DEFAULT '', duration REAL DEFAULT 0,
                language TEXT DEFAULT '', model TEXT DEFAULT '', segments TEXT DEFAULT '[]',
                meeting_date TEXT DEFAULT '', attendees TEXT DEFAULT '',
                location TEXT DEFAULT '', chair TEXT DEFAULT '', agenda TEXT DEFAULT '',
                summary TEXT DEFAULT '', minutes TEXT DEFAULT '', memo TEXT DEFAULT '', actions TEXT DEFAULT '',
                notes TEXT DEFAULT ''
            )''')
            # Backwards-compatible migration for existing users of SolScribe v0.1.
            existing = {r['name'] for r in conn.execute('PRAGMA table_info(sessions)')}
            if 'summary' not in existing:
                conn.execute("ALTER TABLE sessions ADD COLUMN summary TEXT DEFAULT ''")
            conn.execute('CREATE INDEX IF NOT EXISTS ix_sessions_updated ON sessions(updated_at DESC)')

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.database, timeout=15)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        result = dict(row)
        try:
            result['segments'] = json.loads(result.get('segments') or '[]')
        except (json.JSONDecodeError, TypeError):
            result['segments'] = []
        return result

    def create(self, title='Untitled session', audio_path=''):
        session_id = uuid.uuid4().hex
        now = timestamp()
        with self.connect() as con:
            con.execute('INSERT INTO sessions (id, created_at, updated_at, title, audio_path, meeting_date) VALUES (?, ?, ?, ?, ?, ?)',
                        (session_id, now, now, title, str(audio_path), datetime.now().date().isoformat()))
        return session_id

    def get(self, session_id):
        with self.connect() as con:
            row = con.execute('SELECT * FROM sessions WHERE id = ?', (session_id,)).fetchone()
        return self._decode(row)

    def list(self, query=''):
        with self.connect() as con:
            if query:
                rows = con.execute('SELECT * FROM sessions WHERE title LIKE ? ORDER BY updated_at DESC',
                                   ('%' + query + '%',)).fetchall()
            else:
                rows = con.execute('SELECT * FROM sessions ORDER BY updated_at DESC').fetchall()
        return [self._decode(row) for row in rows]

    def update(self, session_id, **values):
        values = {k: v for k, v in values.items() if k in FIELDS and k != 'updated_at'}
        if not values:
            return
        if 'segments' in values:
            values['segments'] = json.dumps(values['segments'], ensure_ascii=False)
        values['updated_at'] = timestamp()
        assignments = ', '.join(f'{field} = ?' for field in values)
        with self.connect() as con:
            con.execute(f'UPDATE sessions SET {assignments} WHERE id = ?', (*values.values(), session_id))

    def delete(self, session_id):
        session = self.get(session_id)
        if not session:
            return
        with self.connect() as con:
            con.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
        # Remove only recordings created by this app; never remove imported files.
        if session.get('audio_path'):
            source = Path(session['audio_path'])
            try:
                if source.resolve().parent == self.recordings.resolve() and source.exists():
                    source.unlink()
            except OSError:
                pass

    def demo(self):
        session_id = self.create('Sample · Weekly project meeting')
        example = [
            (2, 9, 'Welcome everyone. Today we need to review the website launch and agree on next steps.'),
            (10, 19, 'The landing page is complete. The mobile navigation still needs testing before launch.'),
            (20, 31, 'I will finish the mobile testing by Friday and send the report to the team.'),
            (32, 40, 'We agreed to move the release to next Tuesday if the tests pass.'),
            (41, 51, 'The marketing team will prepare the announcement before Monday afternoon.'),
            (52, 62, 'Please make sure the budget spreadsheet is updated. We will review it at the next meeting.'),
        ]
        self.update(session_id, duration=62, language='en', model='demo',
                    attendees='Project team', agenda='Website launch; mobile testing; marketing',
                    segments=[{'start': a, 'end': b, 'speaker': 'Speaker', 'text': t}
                              for a, b, t in example])
        return session_id

"""Transactional meeting repository, explicit audio ownership and recoverable deletion."""
from __future__ import annotations
from contextlib import closing, contextmanager
from datetime import datetime
import json
import logging
import math
import os
from pathlib import Path
import sqlite3
import uuid

from .filesystem import contained_file, write_json

log = logging.getLogger(__name__)
FIELDS = {'title', 'audio_path', 'duration', 'language', 'model', 'segments',
          'meeting_date', 'attendees', 'location', 'chair', 'agenda', 'summary', 'minutes',
          'memo', 'actions', 'notes', 'updated_at', 'action_items', 'transcript_history', 'recording_state', 'recording_pid', 'notes_warnings', 'reviewed_at'}
FIELDS |= {'session_type', 'study_notes', 'study_items', 'study_source_hash', 'study_warnings'}
JSON_FIELDS = {'segments': [], 'action_items': [], 'transcript_history': [], 'notes_warnings': [],
               'study_items': [], 'study_warnings': []}


def data_dir() -> Path:
    root = (Path(os.getenv('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local') if os.name == 'nt'
            else Path(os.getenv('XDG_DATA_HOME') or Path.home() / '.local' / 'share'))
    path = root / 'SolScribe'
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec='microseconds')


class Store:
    def __init__(self, root: Path | None = None):
        self.root = Path(root) if root is not None else data_dir()
        self.root.mkdir(parents=True, exist_ok=True)
        self.recordings = self.root / 'recordings'
        self.models = self.root / 'models'
        self.backups = self.root / 'backups'
        self.drafts = self.root / 'drafts'
        for path in (self.recordings, self.models, self.backups, self.drafts):
            path.mkdir(exist_ok=True)
        self.database = self.root / 'solscribe.db'
        self.recovery_notices: list[str] = []
        existing = self.database.is_file() and self.database.stat().st_size > 0
        if existing:
            with closing(sqlite3.connect(self.database, timeout=3)) as connection:
                if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise sqlite3.DatabaseError('Meeting database needs recovery from a backup')
                version = connection.execute('PRAGMA user_version').fetchone()[0]
            backups = sorted(self.backups.glob('auto-*.db'))
            if version > 5:
                raise sqlite3.DatabaseError('This library needs a newer version of SolScribe')
            if version < 5 or not backups or datetime.fromtimestamp(backups[-1].stat().st_mtime).date() != datetime.now().date():
                self.backup_database(self.backups / f'auto-{datetime.now():%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.db')
                for old in sorted(self.backups.glob('auto-*.db'))[:-5]:
                    old.unlink()
        with self.connect() as conn:
            conn.execute('''CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                title TEXT NOT NULL, audio_path TEXT DEFAULT '', duration REAL DEFAULT 0,
                language TEXT DEFAULT '', model TEXT DEFAULT '', segments TEXT DEFAULT '[]',
                meeting_date TEXT DEFAULT '', attendees TEXT DEFAULT '', location TEXT DEFAULT '',
                chair TEXT DEFAULT '', agenda TEXT DEFAULT '', summary TEXT DEFAULT '',
                minutes TEXT DEFAULT '', memo TEXT DEFAULT '', actions TEXT DEFAULT '', notes TEXT DEFAULT ''
            )''')
            columns = {row['name'] for row in conn.execute('PRAGMA table_info(sessions)')}
            for name, definition in {'summary': "TEXT DEFAULT ''", 'deleted_at': "TEXT DEFAULT ''",
                                     'action_items': "TEXT DEFAULT '[]'", 'transcript_history': "TEXT DEFAULT '[]'",
                                     'recording_state': "TEXT DEFAULT ''", 'recording_pid': 'INTEGER DEFAULT 0', 'notes_warnings': "TEXT DEFAULT '[]'", 'reviewed_at': "TEXT DEFAULT ''",
                                     'session_type': "TEXT DEFAULT 'meeting'", 'study_notes': "TEXT DEFAULT ''",
                                     'study_items': "TEXT DEFAULT '[]'", 'study_source_hash': "TEXT DEFAULT ''",
                                     'study_warnings': "TEXT DEFAULT '[]'"}.items():
                if name not in columns:
                    conn.execute(f'ALTER TABLE sessions ADD COLUMN {name} {definition}')
            conn.execute('''CREATE TABLE IF NOT EXISTS recordings (
                id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE, owned INTEGER NOT NULL DEFAULT 0,
                state TEXT NOT NULL DEFAULT 'ready')''')
            conn.execute('''CREATE TABLE IF NOT EXISTS session_recordings (
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                recording_id TEXT NOT NULL REFERENCES recordings(id), role TEXT NOT NULL,
                PRIMARY KEY(session_id, role))''')
            link_columns = {row['name'] for row in conn.execute('PRAGMA table_info(session_recordings)')}
            if 'offset_seconds' not in link_columns:
                conn.execute('ALTER TABLE session_recordings ADD COLUMN offset_seconds REAL DEFAULT 0')
            # Legacy files have unknown provenance, even inside the recordings
            # folder. Never promote them to owned based only on their location.
            for row in conn.execute("SELECT id, audio_path FROM sessions WHERE audio_path != ''").fetchall():
                linked = conn.execute('SELECT 1 FROM session_recordings WHERE session_id=? AND role=?', (row['id'], 'main')).fetchone()
                if not linked:
                    self._link(conn, row['id'], row['audio_path'], 'main', False, legacy=True)
            conn.execute('CREATE INDEX IF NOT EXISTS ix_sessions_updated ON sessions(updated_at DESC)')
            conn.execute('CREATE INDEX IF NOT EXISTS ix_recording_refs ON session_recordings(recording_id)')
            conn.execute('PRAGMA user_version=5')
        self.recover_drafts()
        self.recover_recordings()

    @contextmanager
    def connect(self, *, write: bool = True):
        connection = sqlite3.connect(self.database, timeout=.25, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _decode(row):
        if row is None:
            return None
        result = dict(row)
        for field in JSON_FIELDS:
            try:
                value = json.loads(result.get(field) or '[]')
                if not isinstance(value, list):
                    raise ValueError('Expected a list')
                if field in ('segments', 'action_items', 'transcript_history') and any(not isinstance(item, dict) for item in value):
                    raise ValueError('Expected records')
                if field == 'segments':
                    from .transcripts import validate_segments
                    validate_segments(value)
                if field == 'study_items':
                    from .lecture import validate_items
                    validate_items(value)
                result[field] = value
            except (ValueError, TypeError):
                # Never turn damaged saved content into an empty editable
                # meeting: autosave could then destroy the original evidence.
                raise sqlite3.DataError(f'Saved {field} needs recovery; original database retained') from None
        result.setdefault('session_type', 'meeting')
        for field in ('study_notes', 'study_source_hash'):
            result.setdefault(field, '')
        if result['session_type'] not in ('meeting', 'lecture'):
            raise sqlite3.DataError('Saved recording mode needs recovery')
        return result

    def _link(self, conn, sid: str, path: str, role: str, owned: bool, *, legacy=False, offset=0.0) -> str:
        if not math.isfinite(float(offset)) or float(offset) < 0:
            raise ValueError('Invalid source-track offset')
        canonical = os.path.normcase(str(Path(path).resolve()))
        if owned and not contained_file(Path(canonical), self.recordings):
            raise ValueError('Owned audio must be inside the managed recordings folder')
        row = conn.execute('SELECT * FROM recordings WHERE path=?', (canonical,)).fetchone()
        if row and row['state'] in ('purging', 'purged'):
            raise ValueError('This recording has been permanently removed')
        if not row:
            if not legacy and not Path(canonical).is_file():
                raise FileNotFoundError('Recording does not exist')
            rid = uuid.uuid4().hex
            conn.execute('INSERT INTO recordings(id,path,owned) VALUES(?,?,?)', (rid, canonical, int(owned)))
        else:
            rid = row['id']
            # Imported/legacy files never acquire ownership implicitly.
            if owned and not row['owned']:
                raise ValueError('Cannot take ownership of an imported or legacy recording')
        conn.execute('INSERT OR REPLACE INTO session_recordings(session_id,recording_id,role,offset_seconds) VALUES(?,?,?,?)', (sid, rid, role, float(offset)))
        return rid

    def create(self, title='Untitled session', audio_path='', *, audio_owned=False, session_type='meeting'):
        if session_type not in ('meeting', 'lecture'):
            raise ValueError('Unknown recording mode')
        sid, now = uuid.uuid4().hex, timestamp()
        with self.connect() as conn:
            conn.execute('INSERT INTO sessions(id,created_at,updated_at,title,audio_path,meeting_date,session_type) VALUES(?,?,?,?,?,?,?)',
                         (sid, now, now, title, str(audio_path), datetime.now().date().isoformat(), session_type))
            if audio_path:
                self._link(conn, sid, str(audio_path), 'main', audio_owned)
        return sid

    def get(self, session_id: str, *, include_deleted=False):
        with self.connect(write=False) as conn:
            row = conn.execute('SELECT * FROM sessions WHERE id=?' + ('' if include_deleted else " AND deleted_at=''"), (session_id,)).fetchone()
        return self._decode(row)

    def list(self, query='', *, deleted=False):
        with self.connect(write=False) as conn:
            rows = conn.execute("SELECT * FROM sessions WHERE (deleted_at != '')=? AND title LIKE ? ORDER BY updated_at DESC, rowid DESC",
                                (int(deleted), '%' + query + '%')).fetchall()
        return [self._decode(row) for row in rows]

    def update(self, session_id: str, *, audio_owned=False, source_tracks=None, **values):
        values = {key: value for key, value in values.items() if key in FIELDS and key != 'updated_at'}
        if not values:
            return
        if 'session_type' in values and values['session_type'] not in ('meeting', 'lecture'):
            raise ValueError('Unknown recording mode')
        if 'study_items' in values:
            from .lecture import validate_items
            validate_items(values['study_items'])
        for field in JSON_FIELDS:
            if field in values and not isinstance(values[field], list):
                raise ValueError(f'{field} must be a list')
        if 'segments' in values:
            from .transcripts import validate_segments
            validate_segments(values['segments'])
        for field in ('action_items', 'transcript_history'):
            if field in values and any(not isinstance(item, dict) for item in values[field]):
                raise ValueError(f'{field} must contain records')
        # A small independent draft can survive a failed/locked DB commit.
        # If the disk cannot hold even this file, the caller retains edits in UI.
        draft = self.drafts / f'{session_id}.json'
        if not session_id or any(c not in '0123456789abcdef' for c in session_id):
            raise ValueError('Invalid session identifier')
        payload = {'id': session_id, 'saved_at': timestamp(), 'values': values,
                   'audio_owned': audio_owned, 'source_tracks': source_tracks}
        write_json(draft, payload)
        encoded = {key: json.dumps(value, ensure_ascii=False, allow_nan=False) if key in JSON_FIELDS else value for key, value in values.items()}
        encoded['updated_at'] = payload['saved_at']
        with self.connect() as conn:
            if not conn.execute("SELECT 1 FROM sessions WHERE id=? AND deleted_at=''", (session_id,)).fetchone():
                raise KeyError('Meeting no longer exists')
            if 'audio_path' in values:
                conn.execute("DELETE FROM session_recordings WHERE session_id=? AND role='main'", (session_id,))
                if values['audio_path']:
                    self._link(conn, session_id, values['audio_path'], 'main', audio_owned)
            if source_tracks is not None:
                for role, path in source_tracks.items():
                    if role not in ('microphone', 'system'):
                        raise ValueError('Unknown recording track')
                    actual_path = path['path'] if isinstance(path, dict) else path
                    self._link(conn, session_id, actual_path, role, audio_owned, offset=path.get('offset', 0) if isinstance(path, dict) else 0)
            assignments = ', '.join(f'{field}=?' for field in encoded)
            conn.execute(f'UPDATE sessions SET {assignments} WHERE id=?', (*encoded.values(), session_id))
        draft.unlink(missing_ok=True)

    def delete(self, session_id: str):
        """Move the meeting into recoverable trash; never unlink any media."""
        with self.connect() as conn:
            conn.execute("UPDATE sessions SET deleted_at=?,updated_at=? WHERE id=? AND deleted_at=''", (timestamp(), timestamp(), session_id))

    def restore(self, session_id: str):
        with self.connect() as conn:
            conn.execute("UPDATE sessions SET deleted_at='',updated_at=? WHERE id=?", (timestamp(), session_id))

    def purge(self, session_id: str, *, confirm=False):
        """Permanently remove a trashed meeting. Media requires separate confirmation."""
        if not confirm:
            raise PermissionError('Permanent deletion requires confirmation')
        if not session_id or any(c not in '0123456789abcdef' for c in session_id):
            raise ValueError('Invalid session identifier')
        with self.connect() as conn:
            row = conn.execute('SELECT deleted_at FROM sessions WHERE id=?', (session_id,)).fetchone()
            if row and not row['deleted_at']:
                raise ValueError('Move the meeting to trash first')
            conn.execute('DELETE FROM sessions WHERE id=?', (session_id,))
        (self.drafts / f'{session_id}.json').unlink(missing_ok=True)

    def recording_references(self, recording_id: str) -> list[str]:
        with self.connect(write=False) as conn:
            return [row[0] for row in conn.execute('SELECT session_id FROM session_recordings WHERE recording_id=?', (recording_id,))]

    def recording_assets(self, session_id: str) -> list[dict]:
        with self.connect(write=False) as conn:
            return [dict(row) for row in conn.execute('SELECT r.*,s.role,s.offset_seconds FROM recordings r JOIN session_recordings s ON r.id=s.recording_id WHERE s.session_id=?', (session_id,))]

    def purge_recording(self, recording_id: str, *, confirm=False):
        if not confirm:
            raise PermissionError('Permanently deleting audio requires confirmation')
        with self.connect() as conn:
            row = conn.execute('SELECT * FROM recordings WHERE id=?', (recording_id,)).fetchone()
            if not row:
                return
            if not row['owned'] or not contained_file(Path(row['path']), self.recordings):
                raise PermissionError('Imported and legacy audio is never deleted automatically')
            if conn.execute('SELECT 1 FROM session_recordings WHERE recording_id=?', (recording_id,)).fetchone():
                raise ValueError('Recording is still referenced by a meeting or trash item')
            # Durable intent prevents another process attaching a new reference
            # between committing and unlinking, and is recoverable after a crash.
            conn.execute("UPDATE recordings SET state='purging' WHERE id=?", (recording_id,))
        Path(row['path']).unlink(missing_ok=True)
        with self.connect() as conn:
            conn.execute("UPDATE recordings SET state='purged' WHERE id=?", (recording_id,))

    def backup_database(self, destination: Path | None = None) -> Path:
        from .backups import snapshot_database
        destination = Path(destination) if destination else self.backups / f'manual-{uuid.uuid4().hex}.db'
        return snapshot_database(self.database, destination)

    def backup_archive(self, destination: Path) -> Path:
        from .backups import create_archive
        return create_archive(self, Path(destination))

    def restore_archive(self, source: Path, *, confirm=False):
        from .backups import restore_archive
        if not confirm:
            raise PermissionError('Restoring a backup requires confirmation')
        restore_archive(self.root, Path(source))

    def restore_database(self, source: Path, *, confirm=False):
        from .backups import restore_database
        if not confirm:
            raise PermissionError('Restoring a database requires confirmation')
        restore_database(self.root, Path(source))

    def recover_drafts(self):
        for path in self.drafts.glob('*.json'):
            try:
                payload = json.loads(path.read_text(encoding='utf-8'))
                session = self.get(payload['id'])
                if not session or payload['saved_at'] <= session['updated_at']:
                    continue
                values = payload['values']
                if not isinstance(values, dict) or not set(values) <= FIELDS:
                    raise ValueError('Invalid recovery draft')
                self.update(payload['id'], audio_owned=payload.get('audio_owned', False),
                            source_tracks=payload.get('source_tracks'), **values)
                self.recovery_notices.append('Recovered unsaved meeting edits.')
            except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
                log.warning('A recovery draft could not be applied; retained for inspection')

    def recover_recordings(self):
        from .recovery import recover_pcm_wave
        from .processes import process_alive
        with self.connect(write=False) as conn:
            pending = [row[0] for row in conn.execute("SELECT id FROM recordings WHERE state='purging'")]
        for recording_id in pending:
            try:
                self.purge_recording(recording_id, confirm=True)
            except (OSError, ValueError, PermissionError):
                log.warning('Previously confirmed audio deletion could not finish')
        with self.connect(write=False) as conn:
            rows = conn.execute("SELECT DISTINCT r.* FROM recordings r JOIN session_recordings s ON r.id=s.recording_id JOIN sessions m ON m.id=s.session_id WHERE r.owned=1 AND m.recording_state='active'").fetchall()
        for row in rows:
            try:
                with self.connect(write=False) as conn:
                    owners = [item[0] for item in conn.execute("SELECT m.recording_pid FROM sessions m JOIN session_recordings s ON m.id=s.session_id WHERE s.recording_id=? AND m.recording_state='active'", (row['id'],))]
                if any(process_alive(int(pid or 0)) for pid in owners):
                    continue
                if not contained_file(Path(row['path']), self.recordings):
                    continue
                info = recover_pcm_wave(Path(row['path']))
                with self.connect() as conn:
                    conn.execute("UPDATE sessions SET recording_state='recovered',recording_pid=0,duration=? WHERE id IN (SELECT session_id FROM session_recordings WHERE recording_id=? AND role='main')", (info['duration'], row['id']))
                self.recovery_notices.append('Recovered audio written before an interrupted recording.')
            except (OSError, ValueError):
                log.warning('An interrupted recording could not be repaired; original retained')

    def demo_lecture(self):
        sid = self.create('Sample · How plants use light', session_type='lecture')
        words = [
            'Photosynthesis is a process that converts light energy into chemical energy.',
            'Chlorophyll is a green pigment that absorbs light. It is not an energy source itself.',
            'For example, a leaf exposed to light can make sugars from carbon dioxide and water.',
            'A limiting factor means a condition that restricts the rate of a process.',
            'For instance, adding more light does not increase the rate when carbon dioxide is limiting.',
            'Remember to distinguish correlation from causation when interpreting a graph.']
        self.update(sid, segments=[{'start': i * 30.0, 'end': i * 30.0 + 20,
                    'speaker': 'Lecturer', 'text': text} for i, text in enumerate(words)], model='sample text')
        return sid

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

"""Validated local backups. Restores stage and verify all data before replacement."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
import uuid
import zipfile

from .filesystem import atomic_destination

MAX_BACKUP_BYTES = 64 * 1024 ** 3


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def validate_database(path: Path) -> None:
    with sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True) as connection:
        if connection.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
            raise ValueError('Backup database failed its integrity check')
        columns = {row[1] for row in connection.execute('PRAGMA table_info(sessions)')}
        if not {'id', 'title', 'created_at', 'updated_at', 'audio_path', 'segments'} <= columns:
            raise ValueError('This is not a SolScribe meeting database')
        from .repository import Store
        connection.row_factory = sqlite3.Row
        for row in connection.execute('SELECT * FROM sessions'):
            Store._decode(row)


def snapshot_database(source: Path, destination: Path) -> Path:
    source, destination = Path(source), Path(destination)
    if source.resolve() == destination.resolve():
        raise ValueError('A backup cannot overwrite the live database')
    with atomic_destination(destination) as temporary:
        with sqlite3.connect(source.resolve().as_uri() + '?mode=ro', uri=True, timeout=3) as original:
            with sqlite3.connect(temporary) as backup:
                original.backup(backup, pages=128, sleep=.02)
        validate_database(temporary)
    return destination


def restore_database(root: Path, source: Path) -> None:
    """Restore a local DB-only snapshot; recordings remain in place."""
    root, source = Path(root), Path(source)
    current = root / 'solscribe.db'
    if current.resolve() == source.resolve():
        raise ValueError('Choose a backup rather than the live database')
    validate_database(source)
    backups = root / 'backups'
    backups.mkdir(parents=True, exist_ok=True)
    if current.is_file():
        wal = Path(str(current) + '-wal')
        if wal.is_file() and wal.stat().st_size:
            raise RuntimeError('Close other SolScribe instances before restoring')
        preserved = backups / f'before-restore-{uuid.uuid4().hex}.db'
        try:
            snapshot_database(current, preserved)
        except (sqlite3.DatabaseError, ValueError):
            with atomic_destination(preserved) as temporary:
                shutil.copyfile(current, temporary)
    with atomic_destination(current) as temporary:
        snapshot_database(source, temporary)


def create_archive(store, destination: Path) -> Path:
    with tempfile.TemporaryDirectory(prefix='.backup-', dir=store.root) as directory:
        snapshot = snapshot_database(store.database, Path(directory) / 'solscribe.db')
        # Read asset metadata from the same snapshot as the archived sessions.
        with sqlite3.connect(snapshot) as connection:
            assets = connection.execute("SELECT id,path FROM recordings WHERE owned=1 AND state NOT IN ('purging','purged')").fetchall()
        manifest = {'version': 1, 'database_sha256': digest(snapshot), 'assets': []}
        with atomic_destination(destination) as temporary:
            with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
                archive.write(snapshot, 'solscribe.db')
                for rid, filename in assets:
                    path = Path(filename)
                    if not path.resolve().is_relative_to(store.recordings.resolve()) or not path.is_file():
                        raise ValueError('An owned recording is missing or outside managed storage')
                    name = f'recordings/{rid}{path.suffix.lower()}'
                    checksum = hashlib.sha256()
                    with path.open('rb') as original, archive.open(name, 'w', force_zip64=True) as output:
                        for block in iter(lambda: original.read(1024 * 1024), b''):
                            checksum.update(block)
                            output.write(block)
                    manifest['assets'].append({'id': rid, 'name': name, 'sha256': checksum.hexdigest()})
                archive.writestr('manifest.json', json.dumps(manifest))
    return destination


def restore_archive(root: Path, source: Path) -> None:
    root, source = Path(root), Path(source)
    root.mkdir(parents=True, exist_ok=True)
    recordings = root / 'recordings'
    recordings.mkdir(exist_ok=True)
    created = []
    committed = False
    try:
        with tempfile.TemporaryDirectory(prefix='.restore-', dir=root) as directory:
            staging = Path(directory)
            with zipfile.ZipFile(source) as archive:
                entries = archive.infolist()
                if len(entries) > 10000 or sum(info.file_size for info in entries) > MAX_BACKUP_BYTES:
                    raise ValueError('Backup exceeds the supported restore size')
                if len({item.filename for item in entries}) != len(entries):
                    raise ValueError('Duplicate paths in backup')
                for info in entries:
                    name = PurePosixPath(info.filename)
                    if name.is_absolute() or '..' in name.parts or '\\' in info.filename or ':' in info.filename:
                        raise ValueError('Unsafe path in backup')
                    if (info.external_attr >> 16) & 0o170000 == 0o120000:
                        raise ValueError('Links are not allowed in backups')
                info = archive.getinfo('manifest.json')
                if info.file_size > 4 * 1024 * 1024:
                    raise ValueError('Backup manifest is too large')
                manifest = json.loads(archive.read(info))
                if not isinstance(manifest, dict) or manifest.get('version') != 1 or not isinstance(manifest.get('assets'), list):
                    raise ValueError('Unsupported backup format')
                expected = {'manifest.json', 'solscribe.db'}
                expected.update(asset['name'] for asset in manifest['assets'])
                if {info.filename for info in entries} != expected:
                    raise ValueError('Backup files do not match its manifest')
                for info in entries:
                    destination = staging / info.filename
                    if not destination.resolve().is_relative_to(staging.resolve()):
                        raise ValueError('Invalid backup destination')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(info) as original, destination.open('wb') as output:
                        shutil.copyfileobj(original, output, length=1024 * 1024)
            database = staging / 'solscribe.db'
            if digest(database) != manifest['database_sha256']:
                raise ValueError('Backup database checksum mismatch')
            validate_database(database)
            for asset in manifest['assets']:
                path = staging / asset['name']
                if digest(path) != asset['sha256']:
                    raise ValueError('Recording checksum mismatch')
                if not asset['id'] or any(c not in '0123456789abcdef' for c in asset['id']):
                    raise ValueError('Invalid recording identifier')
            # Preserve the current DB even when it is corrupt. Do not truncate or
            # reset it just because SQLite cannot open it.
            current = root / 'solscribe.db'
            backup_dir = root / 'backups'
            backup_dir.mkdir(exist_ok=True)
            if current.is_file():
                wal = Path(str(current) + '-wal')
                if wal.is_file() and wal.stat().st_size:
                    raise RuntimeError('Close other SolScribe instances before restoring a backup')
                prior = backup_dir / f'before-restore-{uuid.uuid4().hex}.db'
                try:
                    snapshot_database(current, prior)
                except sqlite3.DatabaseError:
                    with atomic_destination(prior) as temporary:
                        shutil.copyfile(current, temporary)
            with sqlite3.connect(database) as connection:
                for asset in manifest['assets']:
                    name = f'{asset["id"]}-{uuid.uuid4().hex[:8]}{Path(asset["name"]).suffix}'
                    destination = recordings / name
                    with atomic_destination(destination) as temporary:
                        shutil.copyfile(staging / asset['name'], temporary)
                    created.append(destination)
                    row = connection.execute('SELECT path FROM recordings WHERE id=? AND owned=1', (asset['id'],)).fetchone()
                    if not row:
                        raise ValueError('Backup contains an unregistered recording')
                    connection.execute("UPDATE sessions SET audio_path=? WHERE id IN (SELECT session_id FROM session_recordings WHERE recording_id=? AND role='main')", (str(destination), asset['id']))
                    connection.execute('UPDATE recordings SET path=? WHERE id=?', (str(destination), asset['id']))
            with atomic_destination(current) as temporary:
                shutil.copyfile(database, temporary)
            committed = True
    except (KeyError, TypeError, zipfile.BadZipFile) as exc:
        raise ValueError('Backup is incomplete or invalid') from exc
    finally:
        if not committed:
            for path in created:
                path.unlink(missing_ok=True)

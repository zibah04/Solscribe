import json
import sqlite3
import struct
import wave
import zipfile

import pytest

from solscribe.storage import Store
from solscribe.backups import restore_archive
from solscribe.recovery import recover_pcm_wave


def wav(path, frames=1600):
    with wave.open(str(path), 'wb') as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16000)
        output.writeframes(b'\x01\x00' * frames)
    return path


def test_shared_owned_audio_requires_all_references_to_be_purged(tmp_path):
    store = Store(tmp_path)
    audio = wav(store.recordings / 'shared.wav')
    first = store.create('First', str(audio), audio_owned=True)
    second = store.create('Second', str(audio))
    rid = store.recording_assets(first)[0]['id']
    store.delete(first)
    assert audio.exists() and store.get(second)
    with pytest.raises(ValueError, match='referenced'):
        store.purge_recording(rid, confirm=True)
    store.purge(first, confirm=True)
    assert audio.exists()
    with pytest.raises(ValueError, match='referenced'):
        store.purge_recording(rid, confirm=True)
    store.delete(second)
    store.purge(second, confirm=True)
    with pytest.raises(PermissionError):
        store.purge_recording(rid)
    store.purge_recording(rid, confirm=True)
    assert not audio.exists()


@pytest.mark.parametrize('inside', [True, False])
def test_imported_files_are_never_owned_or_removed(tmp_path, inside):
    store = Store(tmp_path / 'store')
    audio = wav((store.recordings if inside else tmp_path) / 'imported.wav')
    sid = store.create('Import', str(audio))
    asset = store.recording_assets(sid)[0]
    assert not asset['owned']
    store.delete(sid)
    store.purge(sid, confirm=True)
    with pytest.raises(PermissionError):
        store.purge_recording(asset['id'], confirm=True)
    assert audio.exists()


def test_recoverable_trash_preserves_documents_and_audio(tmp_path):
    store = Store(tmp_path)
    audio = wav(store.recordings / 'meeting.wav')
    sid = store.create('Meeting', str(audio), audio_owned=True)
    store.update(sid, summary='Edited summary', action_items=[{'task': 'Email report'}])
    store.delete(sid)
    assert not store.list() and store.get(sid) is None
    assert store.list(deleted=True)[0]['summary'] == 'Edited summary'
    store.restore(sid)
    assert store.get(sid)['action_items'] == [{'task': 'Email report'}]
    assert audio.exists()
    with pytest.raises(ValueError):
        store.purge(sid, confirm=True)


def test_owned_path_cannot_escape_managed_storage(tmp_path):
    store = Store(tmp_path / 'data')
    audio = wav(tmp_path / 'external.wav')
    with pytest.raises(ValueError, match='managed'):
        store.create('Unsafe ownership', str(audio), audio_owned=True)
    assert store.list() == [] and audio.exists()


def test_archive_restores_audio_and_notes_in_a_different_folder(tmp_path):
    store = Store(tmp_path / 'original')
    audio = wav(store.recordings / 'source.wav')
    external = wav(tmp_path / 'external.wav')
    sid = store.create('Keep this', str(audio), audio_owned=True)
    store.update(sid, summary='Carefully edited', segments=[{'start': 0, 'end': .1, 'speaker': 'Alice', 'text': 'Hello'}])
    imported = store.create('Linked file', str(external))
    archive = store.backup_archive(tmp_path / 'backup.zip')
    target = Store(tmp_path / 'restored')
    previous = target.create('Existing destination work')
    with pytest.raises(PermissionError):
        target.restore_archive(archive)
    target.restore_archive(archive, confirm=True)
    restored = target.get(sid)
    assert restored['summary'] == 'Carefully edited'
    assert restored['segments'][0]['speaker'] == 'Alice'
    new_audio = __import__('pathlib').Path(restored['audio_path'])
    assert new_audio.parent == target.recordings and new_audio.read_bytes() == audio.read_bytes()
    assert target.get(imported)['audio_path'] == str(external)
    assert external.exists() and audio.exists()
    # Replaced work is retained in the pre-restore database snapshot.
    backups = list(target.backups.glob('before-restore-*.db'))
    with sqlite3.connect(backups[0]) as connection:
        assert connection.execute('SELECT title FROM sessions WHERE id=?', (previous,)).fetchone()[0] == 'Existing destination work'


@pytest.mark.parametrize('bad_name', ['../escape.txt', '/absolute.txt', 'C:/outside.txt', 'recordings/../../oops'])
def test_unsafe_archives_do_not_change_current_data(tmp_path, bad_name):
    store = Store(tmp_path / 'data')
    sid = store.create('Keep me')
    backup = tmp_path / 'bad.zip'
    with zipfile.ZipFile(backup, 'w') as archive:
        archive.writestr(bad_name, 'bad')
    with pytest.raises(ValueError):
        store.restore_archive(backup, confirm=True)
    assert store.get(sid)['title'] == 'Keep me'


def test_tampered_backup_is_rejected_without_changing_work(tmp_path):
    store = Store(tmp_path / 'data')
    sid = store.create('Keep me')
    original = store.backup_archive(tmp_path / 'valid.zip')
    bad = tmp_path / 'bad.zip'
    with zipfile.ZipFile(original) as source, zipfile.ZipFile(bad, 'w') as dest:
        for info in source.infolist():
            dest.writestr(info.filename, b'tampered' if info.filename == 'solscribe.db' else source.read(info))
    with pytest.raises(ValueError, match='checksum'):
        store.restore_archive(bad, confirm=True)
    assert store.get(sid)['title'] == 'Keep me'


def test_failed_commit_retains_a_draft_and_recovers_on_restart(tmp_path, monkeypatch):
    from contextlib import contextmanager
    store = Store(tmp_path)
    sid = store.create('Draft')
    original = store.connect
    @contextmanager
    def locked(**kwargs):
        if kwargs.get('write', True):
            raise sqlite3.OperationalError('database is locked')
        with original(**kwargs) as connection:
            yield connection
    monkeypatch.setattr(store, 'connect', locked)
    with pytest.raises(sqlite3.OperationalError):
        store.update(sid, summary='Recover this text')
    assert list(store.drafts.glob('*.json'))
    restored = Store(tmp_path)
    assert restored.get(sid)['summary'] == 'Recover this text'
    assert not list(restored.drafts.glob('*.json'))


def test_interrupted_wav_sizes_repaired_only_for_owned_active_capture(tmp_path):
    store = Store(tmp_path)
    audio = wav(store.recordings / 'interrupted.wav')
    sid = store.create('Interrupted', str(audio), audio_owned=True)
    store.update(sid, recording_state='active')
    with audio.open('r+b') as stream:
        stream.seek(4); stream.write(struct.pack('<I', 36))
        stream.seek(40); stream.write(struct.pack('<I', 0))
    restored = Store(tmp_path)
    assert restored.get(sid)['recording_state'] == 'recovered'
    with wave.open(str(audio)) as repaired:
        assert repaired.getnframes() == 1600
    assert restored.recovery_notices


def test_recovery_rejects_non_wav_without_modifying_it(tmp_path):
    path = tmp_path / 'unknown.wav'
    path.write_bytes(b'private imported content' * 4)
    before = path.read_bytes()
    with pytest.raises(ValueError):
        recover_pcm_wave(path)
    assert path.read_bytes() == before


def test_live_process_recording_is_not_repaired_on_another_store_open(tmp_path):
    import os
    store = Store(tmp_path)
    audio = wav(store.recordings / 'still-active.wav')
    sid = store.create('Still recording', str(audio), audio_owned=True)
    store.update(sid, recording_state='active', recording_pid=os.getpid())
    before = audio.read_bytes()
    reopened = Store(tmp_path)
    assert reopened.get(sid)['recording_state'] == 'active'
    assert audio.read_bytes() == before


def test_raw_database_restore_quarantines_corrupt_current_database(tmp_path):
    from solscribe.backups import restore_database
    store = Store(tmp_path)
    sid = store.create('Recover this meeting')
    snapshot = store.backup_database(tmp_path / 'snapshot.db')
    corrupt = b'This is the damaged original database'
    store.database.write_bytes(corrupt)
    restore_database(tmp_path, snapshot)
    assert Store(tmp_path).get(sid)['title'] == 'Recover this meeting'
    assert any(path.read_bytes() == corrupt for path in store.backups.glob('before-restore-*.db'))


@pytest.mark.parametrize('content', ['{broken', '[42]', '{"unexpected": "object"}'])
def test_damaged_saved_transcript_is_not_silently_replaced(tmp_path, content):
    store = Store(tmp_path)
    sid = store.create('Damaged content')
    with store.connect() as connection:
        connection.execute('UPDATE sessions SET segments=? WHERE id=?', (content, sid))
    with pytest.raises(sqlite3.DataError, match='original database retained'):
        store.get(sid)
    with store.connect(write=False) as connection:
        assert connection.execute('SELECT segments FROM sessions WHERE id=?', (sid,)).fetchone()[0] == content


def test_migration_creates_a_pre_upgrade_backup_and_preserves_legacy_audio(tmp_path):
    store = Store(tmp_path)
    audio = wav(store.recordings / 'legacy.wav')
    sid = store.create('Old work', str(audio))
    with sqlite3.connect(store.database) as conn:
        conn.execute('PRAGMA user_version=0')
        conn.execute('DELETE FROM session_recordings')
        conn.execute('DELETE FROM recordings')
    migrated = Store(tmp_path)
    assert migrated.get(sid)['title'] == 'Old work'
    assert migrated.recording_assets(sid)[0]['owned'] == 0
    assert list(migrated.backups.glob('auto-*.db')) and audio.exists()


def test_corrupt_database_is_not_silently_reset(tmp_path):
    database = tmp_path / 'solscribe.db'
    database.write_bytes(b'not a database')
    with pytest.raises(sqlite3.DatabaseError):
        Store(tmp_path)
    assert database.read_bytes() == b'not a database'

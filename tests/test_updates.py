"""Update versioning, trusted downloads, atomic failure and install handoff."""
import hashlib
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtNetwork import QNetworkRequest, QNetworkReply

from test_live_ui import app, window, until
from solscribe.updates import Update, select_update, version_key, trusted_url, verify_installer
from solscribe.update_transport import UpdateClient

DATA = b'An installer fixture; never executed.' * 50
DIGEST = hashlib.sha256(DATA).hexdigest()


def release(tag='v0.5.0-beta.1', **asset_values):
    key = version_key(tag)
    filename = f'SolScribe-Setup-{key[0]}.{key[1]}.{key[2]}.exe'
    asset = {'name': filename, 'browser_download_url': f'https://github.com/zibah04/Solscribe/releases/download/{tag}/{filename}',
             'size': len(DATA), 'digest': 'sha256:' + DIGEST, **asset_values}
    return {'tag_name': tag, 'draft': False, 'prerelease': key[3] < 3, 'assets': [asset]}


def update():
    return select_update([release()], 'v0.4.1-beta.1')


def test_versions_sort_numeric_core_prereleases_and_stable_correctly():
    versions = ['v0.4.1-alpha.1', 'v0.4.1-beta.1', 'v0.4.1-beta.2', 'v0.4.1-rc.1', 'v0.4.1', 'v0.4.2', 'v0.10.0']
    assert sorted(reversed(versions), key=version_key) == versions


@pytest.mark.parametrize('tag', ['latest', 'v0.4', 'v0.4.1/../../bad', 'v0.4.1-beta.01'])
def test_invalid_tags_are_rejected(tag):
    with pytest.raises(ValueError):
        version_key(tag)


def test_no_downgrades_drafts_or_unrequested_preview_releases():
    draft = {**release('v1.0.0'), 'draft': True}
    assert select_update([release('v0.4.0-beta.1'), draft], 'v0.4.1-beta.1') is None
    assert select_update([release()], 'v0.4.1', include_previews=False) is None
    assert select_update([release('v0.5.0'), release()], 'v0.4.1').tag == 'v0.5.0'


@pytest.mark.parametrize('fields', [{'digest': None}, {'digest': 'sha256:bad'}, {'size': -1}, {'size': 2**40},
    {'browser_download_url': 'https://evil.example/download.exe'}, {'browser_download_url': 'http://github.com/download.exe'}])
def test_invalid_installer_metadata_is_never_offered(fields):
    with pytest.raises(ValueError):
        select_update([release(**fields)], 'v0.4.1-beta.1')


@pytest.mark.parametrize('url', ['http://github.com/zibah04/Solscribe/releases/download/a/b.exe',
    'https://github.com.evil.example/zibah04/Solscribe/releases/download/a/b.exe',
    'https://evil@github.com/zibah04/Solscribe/releases/download/a/b.exe',
    'https://github.com/other/repo/releases/download/a/b.exe', 'file:///tmp/update.exe'])
def test_untrusted_download_addresses_are_rejected(url):
    assert not trusted_url(url, download=True)


def test_api_and_official_cdn_addresses_are_allowed():
    assert trusted_url('https://api.github.com/repos/zibah04/Solscribe/releases?per_page=100')
    assert trusted_url('https://release-assets.githubusercontent.com/example', download=True)


class Reply(QObject):
    readyRead = Signal()
    finished = Signal()
    def __init__(self, request):
        super().__init__()
        self.request, self.body = request, bytearray()
        self.status, self.redirect, self.aborted = 200, None, False
    def setReadBufferSize(self, size): self.buffer_limit = size
    def attribute(self, name):
        if name == QNetworkRequest.HttpStatusCodeAttribute: return self.status
        if name == QNetworkRequest.RedirectionTargetAttribute: return self.redirect
    def bytesAvailable(self): return len(self.body)
    def read(self, count):
        data = bytes(self.body[:count]); del self.body[:count]; return data
    def readAll(self): return self.read(len(self.body))
    def error(self): return QNetworkReply.NoError
    def url(self): return self.request.url()
    def abort(self):
        self.aborted = True
        self.finished.emit()
    def feed(self, data, finish=True):
        self.body.extend(data)
        self.readyRead.emit()
        if finish: self.finished.emit()


class Manager:
    def __init__(self): self.replies = []
    def get(self, request):
        reply = Reply(request)
        self.replies.append(reply)
        return reply


@pytest.fixture
def client(app, tmp_path):
    value = UpdateClient(tmp_path, 'v0.4.1-beta.1')
    value.manager = Manager()
    yield value
    value.cancel()
    value.deleteLater()
    app.processEvents()


def test_check_sends_only_a_public_metadata_get(client):
    import json
    results = []
    client.checked.connect(results.append)
    client.check()
    reply = client.manager.replies[-1]
    assert reply.request.url().host() == 'api.github.com'
    assert reply.buffer_limit <= 256 * 1024
    reply.feed(json.dumps([release()]).encode())
    assert results == [update()] and not client.active


def test_verified_download_is_promoted_only_after_complete_hash_match(client):
    results = []
    client.downloaded.connect(results.append)
    client.download(update())
    reply = client.manager.replies[-1]
    reply.feed(DATA[:100], finish=False)
    assert not (client.root / 'updates' / update().filename).exists()
    reply.feed(DATA[100:])
    assert results == [client.root / 'updates' / update().filename]
    assert results[0].read_bytes() == DATA and not list(results[0].parent.glob('*.part'))


def test_changed_download_preserves_previous_cached_file_and_never_signals_ready(client):
    folder = client.root / 'updates'; folder.mkdir()
    original = folder / update().filename
    original.write_bytes(b'previous good copy')
    errors, results = [], []
    client.failed.connect(errors.append); client.downloaded.connect(results.append)
    client.download(update())
    client.manager.replies[-1].feed(b'x' * len(DATA))
    assert errors and not results and original.read_bytes() == b'previous good copy'
    assert not list(folder.glob('*.part'))


def test_cancel_removes_partial_download(client):
    client.download(update())
    client.manager.replies[-1].feed(DATA[:30], finish=False)
    client.cancel()
    assert not client.active and not list((client.root / 'updates').iterdir())


def test_untrusted_redirect_aborts_without_downloading(client):
    errors = []
    client.failed.connect(errors.append)
    client.download(update())
    reply = client.manager.replies[-1]
    reply.status, reply.redirect = 302, QUrl('https://evil.example/installer.exe')
    reply.feed(b'redirect body')
    assert errors and len(client.manager.replies) == 1 and not client.active
    assert not list((client.root / 'updates').iterdir())


def test_missing_or_changed_cached_installer_is_rejected(tmp_path):
    path = tmp_path / update().filename
    path.write_bytes(DATA)
    assert verify_installer(path, update()) == path
    path.write_bytes(b'x' * len(DATA))
    with pytest.raises(ValueError, match='verified'):
        verify_installer(path, update())


def prepare_window_update(window, monkeypatch):
    folder = window.store.root / 'updates'; folder.mkdir(exist_ok=True)
    path = folder / update().filename; path.write_bytes(DATA)
    window._update_available, window._downloaded_update = update(), path
    monkeypatch.setattr(window, '_supports_update_installation', lambda: True)
    launched = []
    monkeypatch.setattr(window, '_launch_update_installer', launched.append)
    return launched


def test_install_saves_edits_and_backs_up_before_handoff(window, monkeypatch):
    window.load_demo()
    sid = window.session_id
    window.doc_edits['Summary'].setPlainText('Keep my latest edits')
    launched = prepare_window_update(window, monkeypatch)
    window.install_update()
    until(lambda: not window._update_install_active)
    assert launched and not window.isVisible()
    assert window.store.get(sid)['summary'] == 'Keep my latest edits'
    assert list(window.store.backups.glob('manual-*.db'))


def test_failed_update_backup_keeps_app_open_and_does_not_launch(window, monkeypatch):
    launched = prepare_window_update(window, monkeypatch)
    def denied(): raise OSError('disk full')
    monkeypatch.setattr(window.store, 'backup_database', denied)
    window.install_update()
    until(lambda: not window._update_install_active)
    assert window.isVisible() and not launched
    assert 'could not be prepared' in window.update_status_label.text()


def test_recording_blocks_update_installation(window, monkeypatch):
    launched = prepare_window_update(window, monkeypatch)
    window.record_timer.start()
    window.install_update()
    window.record_timer.stop()
    assert not launched and not window._update_install_active
    assert 'Finish the current recording' in window.update_status_label.text()


def test_installer_handoff_uses_windows_normal_file_open(monkeypatch):
    from solscribe.presentation import help_updates
    calls = []
    monkeypatch.setattr(help_updates.os, 'startfile', lambda *args: calls.append(args), raising=False)
    path = Path('installer path with spaces.exe')
    help_updates.HelpUpdates._launch_update_installer(path)
    assert calls == [(str(path), 'open')]


def test_update_checks_are_opt_in_and_throttled(window, monkeypatch, app):
    calls = []
    monkeypatch.setattr(window._update_client, 'check', lambda **kwargs: calls.append(kwargs))
    window.settings.setValue('welcome_seen', True)
    window.start_first_run()
    app.processEvents()
    assert not calls
    window.auto_updates_checkbox.setChecked(True)
    app.processEvents()
    assert calls == [{'include_previews': True}]
    window.settings.setValue('updates_last_checked', time.time())
    window.start_first_run()
    assert not window._update_auto_timer.isActive()

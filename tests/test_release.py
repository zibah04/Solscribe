"""Release regressions: appearance, preserving edits, recording and safe exports."""
import sys
import types

import numpy as np
import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette

from test_live_ui import app, window, until
from solscribe import exporters, ui
from solscribe.recorder import MicrophoneRecorder
from solscribe.themes import THEMES, palette


def contrast(a, b):
    def luminance(color):
        rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    lighter, darker = sorted((luminance(a), luminance(b)), reverse=True)
    return (lighter + .05) / (darker + .05)


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_theme_text_contrast(theme):
    colors = THEMES[theme]
    pairs = [('ink', 'bg'), ('muted', 'bg'), ('ink', 'field'),
             ('muted', 'panel'), ('record_ink', 'record'), ('accent_ink', 'tint')]
    for ink, background in pairs:
        assert contrast(colors[ink], colors[background]) >= 4.5, (theme, ink, background)
    assert contrast('#FFFFFF', colors['accent']) >= 4.5


@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_theme_switch_preserves_edits_and_survives_restart(window, app, theme):
    window.load_demo()
    window.doc_edits['Summary'].setPlainText('My unsaved summary')
    window.table.item(0, 1).setText('Alice')
    window.set_theme(theme)
    assert window.doc_edits['Summary'].toPlainText() == 'My unsaved summary'
    assert window.table.item(0, 1).text() == 'Alice'
    assert window.settings.value('theme') == theme
    assert window.palette().color(QPalette.Text).name() == THEMES[theme]['ink'].lower()
    assert window.persist()
    reopened = ui.MainWindow()
    assert reopened.theme_name == theme
    assert reopened.doc_edits['Summary'].toPlainText() == 'My unsaved summary'
    assert reopened.table.item(0, 1).text() == 'Alice'
    reopened.close()


@pytest.mark.parametrize('theme', ['light', 'dark'])
@pytest.mark.parametrize('size', [(1000, 640), (1280, 680)])
def test_all_pages_fit_small_windows(window, app, theme, size):
    window.set_theme(theme)
    window.load_demo()
    window.resize(*size)
    for index in range(window.tabs.count()):
        window.tabs.setCurrentIndex(index)
        app.processEvents()
        assert window.size().toTuple() == size
        assert window.tabs.currentWidget().height() >= 160
    window.tabs.setCurrentIndex(0)
    assert window.table.viewport().height() >= 160


def test_empty_state_and_keyboard_access(window, app):
    assert window.transcript_stack.currentIndex() == 1
    assert not window.report_btn.isEnabled()
    assert not window.export_btn.isEnabled()
    assert window.theme_combo.accessibleName() == 'Appearance'
    assert window.record_btn.focusPolicy() & Qt.TabFocus
    window.load_demo()
    assert window.transcript_stack.currentIndex() == 0
    assert window.report_btn.isEnabled() and window.export_btn.isEnabled()


def test_failed_save_keeps_edits_and_blocks_discarding_them(window, monkeypatch):
    window.load_demo()
    sid = window.session_id
    window.doc_edits['Summary'].setPlainText('Do not lose this work')
    original_update = window.store.update
    def full_disk(*args, **kwargs):
        raise OSError('disk full')
    monkeypatch.setattr(window.store, 'update', full_disk)
    assert not window.persist()
    window.new_session()
    assert window.session_id == sid
    assert window.doc_edits['Summary'].toPlainText() == 'Do not lose this work'
    assert 'not saved' in window.flow_hint.text()
    monkeypatch.setattr(window, '_show_error', lambda *args: None)
    assert not window.close()
    assert window.isVisible()
    monkeypatch.setattr(window.store, 'update', original_update)
    assert window.persist()
    assert not window._save_error
    assert window.store.get(sid)['summary'] == 'Do not lose this work'


def test_export_failure_never_replaces_an_existing_document(tmp_path, monkeypatch):
    destination = tmp_path / 'important.docx'
    destination.write_bytes(b'original document')
    def partial_then_fail(path, content):
        path.write_bytes(b'partial new data')
        raise OSError('disk full')
    monkeypatch.setattr(exporters, 'write_docx', partial_then_fail)
    with pytest.raises(OSError, match='disk full'):
        exporters.export_file(destination, 'docx', {'minutes': '# New notes'})
    assert destination.read_bytes() == b'original document'
    assert not list(tmp_path.glob('.solscribe-*'))


@pytest.mark.parametrize('name', ['CON', 'nul', 'COM1.txt', 'LPT9', 'PRN'])
def test_windows_export_names_are_usable(name):
    assert exporters.safe_filename(name).startswith('Meeting - ')


def test_subtitle_counters_are_contiguous_after_blank_rows():
    text = exporters.srt_text([{'text': ''}, {'start': 0, 'end': 1, 'text': 'Hello'},
                               {'text': ' '}, {'start': 1, 'end': 2, 'text': 'World'}])
    assert text.startswith('1\n')
    assert '\n2\n' in text
    assert '\n3\n' not in text


def test_microphone_start_failure_closes_stream_and_writer(tmp_path, monkeypatch):
    closed = []
    class Input:
        def __init__(self, **kwargs): pass
        def start(self): raise OSError('microphone denied')
        def stop(self): pass
        def close(self): closed.append(True)
    monkeypatch.setitem(sys.modules, 'sounddevice', types.SimpleNamespace(InputStream=Input))
    recorder = MicrophoneRecorder()
    with pytest.raises(OSError, match='microphone denied'):
        recorder.start(tmp_path / 'audio.wav')
    assert closed and not recorder.active
    assert recorder.stream is None and not recorder.writer.is_alive()


def test_microphone_output_failure_is_reported_before_opening_device(tmp_path, monkeypatch):
    import solscribe.recorder as module
    calls = []
    monkeypatch.setitem(sys.modules, 'sounddevice', types.SimpleNamespace(InputStream=lambda **kw: calls.append(kw)))
    def denied(*args): raise OSError('cannot write')
    monkeypatch.setattr(module.wave, 'open', denied)
    recorder = MicrophoneRecorder()
    with pytest.raises(OSError, match='cannot write'):
        recorder.start(tmp_path / 'audio.wav')
    assert not calls and not recorder.active


def test_microphone_stop_error_still_closes_stream(tmp_path, monkeypatch):
    closed = []
    class Input:
        def __init__(self, **kw): self.callback = kw['callback']
        def start(self): self.callback(np.ones((1024, 1), dtype=np.int16), 1024, None, None)
        def stop(self): raise OSError('device unplugged')
        def close(self): closed.append(True)
    monkeypatch.setitem(sys.modules, 'sounddevice', types.SimpleNamespace(InputStream=Input))
    recorder = MicrophoneRecorder()
    recorder.start(tmp_path / 'audio.wav')
    recorder.stop()
    assert closed and not recorder.active
    assert not recorder.writer.is_alive()
    assert 'device unplugged' in recorder.error


def test_startup_failure_has_a_plain_message_with_optional_details(app, monkeypatch):
    import app as entry
    monkeypatch.setattr(entry, 'QApplication', lambda args: app)
    def unavailable(): raise OSError('database is locked')
    monkeypatch.setattr(entry, 'MainWindow', unavailable)
    shown = []
    monkeypatch.setattr(entry.QMessageBox, 'exec', lambda box: shown.append((box.text(), box.detailedText())))
    assert entry.main() == 1
    assert len(shown) == 1
    assert 'database is locked' not in shown[0][0]
    assert 'database is locked' in shown[0][1]

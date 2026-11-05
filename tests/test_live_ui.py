"""Headless layout and recording-to-caption regressions, without real audio hardware."""
import os
import sys
import time
import types
import wave

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
if sys.platform.startswith('linux'):
    os.environ.setdefault('QT_AUDIO_BACKEND', 'pulseaudio')

import numpy as np
import pytest
from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from solscribe import ui
from solscribe.storage import Store


@pytest.fixture(scope='session')
def app():
    return QApplication.instance() or QApplication([])


def until(predicate, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        QTest.qWait(10)
        if predicate():
            return
    assert predicate(), 'Timed out waiting for Qt worker output'


@pytest.fixture
def window(app, tmp_path, monkeypatch):
    monkeypatch.setattr(ui, 'Store', lambda: Store(tmp_path / 'data'))
    monkeypatch.setattr(ui, 'QSettings', lambda *args: QSettings(str(tmp_path / 'settings.ini'), QSettings.IniFormat))
    monkeypatch.setattr(ui.MicrophoneRecorder, 'devices', staticmethod(lambda: []))
    monkeypatch.setattr(ui.SystemLoopbackRecorder, 'devices', staticmethod(lambda: []))
    monkeypatch.setattr(ui.QMessageBox, 'warning', lambda *args: None)
    w = ui.MainWindow()
    w.show()
    app.processEvents()
    yield w
    if w.record_timer.isActive():
        w.toggle_record()
    if w._live_worker:
        w._live_worker.stop()
        w._live_worker.wait(5000)
    app.processEvents()
    w.close()


@pytest.mark.parametrize('size', [(1000, 640), (1280, 680)])
def test_transcript_has_visible_rows_at_laptop_sizes(window, app, size):
    window.load_demo()
    window.resize(*size)
    app.processEvents()
    assert window.size().toTuple() == size
    assert window.table.viewport().height() >= 160
    assert not window.table.isRowHidden(0)
    assert window.table.rowHeight(0) >= 48
    for control in (window.transcribe_btn, window.play_btn):
        assert control.height() >= control.minimumSizeHint().height()


def install_fake_audio(monkeypatch, samples, model_class):
    class Input:
        def __init__(self, **kwargs):
            self.callback = kwargs['callback']
        def start(self):
            self.callback(samples.reshape(-1, 1), len(samples), None, None)
        def stop(self):
            pass
        def close(self):
            pass
    monkeypatch.setitem(sys.modules, 'sounddevice', types.SimpleNamespace(InputStream=Input))
    monkeypatch.setitem(sys.modules, 'faster_whisper', types.SimpleNamespace(WhisperModel=model_class))


def test_captions_arrive_before_stop_and_preserve_final_short_tail(window, monkeypatch):
    loaded = []
    class Model:
        def __init__(self, name, **kwargs):
            loaded.append(name)
        def transcribe(self, audio, **kwargs):
            return iter([types.SimpleNamespace(start=0, end=len(audio) / 16000, text='Visible while speaking')]), None
    samples = np.full(36000, 1000, dtype=np.int16)  # 2 seconds plus a 250 ms final word.
    install_fake_audio(monkeypatch, samples, Model)
    window.search_transcript.setText('old filter')
    window.toggle_record()
    until(lambda: window.table.rowCount() == 1)
    assert window.record_timer.isActive() and window._live_worker.isRunning()
    assert loaded == ['tiny']
    assert not window.search_transcript.text()
    assert not window.table.isRowHidden(0)
    assert window.table.item(0, 2).text() == 'Visible while speaking'
    assert not window.live_model_combo.isEnabled()
    window.toggle_record()
    until(lambda: not window._live_worker.isRunning())
    until(lambda: window.table.rowCount() == 2)
    parts = window.store.get(window.session_id)['segments']
    assert [(p['start'], p['end']) for p in parts] == [(0, 2), (2, 2.25)]
    with wave.open(str(window.recorder.path), 'rb') as recording:
        assert recording.getnframes() == len(samples)


def test_loading_message_is_not_overwritten_by_recording_meter(window):
    window._live_status('Loading live model · first use downloads it')
    window.recorder.active = True
    window.record_timer.start()
    window._refresh_recording()
    assert 'Loading live model' in window.caption_status.text()
    window.record_timer.stop()
    window.recorder.active = False


def test_silence_does_not_claim_successful_captions(window, monkeypatch):
    class Model:
        def __init__(self, *args, **kwargs):
            pass
        def transcribe(self, *args, **kwargs):
            raise AssertionError('Silence should not reach inference')
    install_fake_audio(monkeypatch, np.zeros(36000, dtype=np.int16), Model)
    window.toggle_record()
    until(lambda: window._live_worker.processed_seconds >= 2)
    window.toggle_record()
    until(lambda: 'No words recognized' in window.caption_status.text())
    assert window.table.rowCount() == 0


def test_caption_failure_remains_visible_during_recording(window, monkeypatch):
    class Model:
        def __init__(self, *args, **kwargs):
            raise RuntimeError('Model download failed')
    install_fake_audio(monkeypatch, np.full(16000, 1000, dtype=np.int16), Model)
    window.toggle_record()
    until(lambda: window._live_failed_message is not None)
    window._refresh_recording()
    assert 'recording is safe' in window.caption_status.text()
    assert 'Model download failed' not in window.caption_status.text()
    assert 'WORDS UNAVAILABLE' in window.status_label.text()
    assert window.record_timer.isActive()


def test_meeting_details_export_shortcut_and_metadata(window):
    window.tabs.setCurrentIndex(5)
    assert window.current_section() == 'Transcript'
    window.attendees_edit.setText('Alice, Bob')
    window.persist()
    assert window.store.get(window.session_id)['attendees'] == 'Alice, Bob'
    window.tabs.setCurrentIndex(6)
    assert window.current_section() == 'Transcript'


def test_missing_writing_helper_creates_notes_without_an_error_popup(window, monkeypatch):
    from urllib.error import URLError
    def unavailable(*args):
        raise URLError('[WinError 10061] Connection refused')
    monkeypatch.setattr(ui, 'draft_ai', unavailable)
    monkeypatch.setattr(window, '_show_error', lambda *args: pytest.fail('Unexpected error popup'))
    window.load_demo()
    sid = window.session_id
    window.engine_combo.setCurrentIndex(window.engine_combo.findData('ai'))
    window.generate_reports()
    until(lambda: not window._is_busy() and bool(window.store.get(sid)['summary']))
    until(lambda: window.notes_details_btn.isVisible())
    saved = window.store.get(sid)
    assert all(saved[field] for field in ('summary', 'minutes', 'memo', 'actions'))
    assert 'landing page' in saved['summary']
    assert 'Quick notes are ready' in window.flow_hint.text()
    assert 'WinError' not in window.flow_hint.text()
    assert 'WinError' in window._notes_details
    assert not window.doc_edits['Summary'].isReadOnly()
    assert window.report_btn.isEnabled()


def test_declining_replacement_preserves_edited_notes(window, monkeypatch):
    window.load_demo()
    window.doc_edits['Summary'].setPlainText('My carefully edited notes')
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: ui.QMessageBox.No)
    window.generate_reports()
    assert window._report_worker is None
    assert window.store.get(window.session_id)['summary'] == 'My carefully edited notes'


def test_save_a_copy_does_not_interrupt_with_an_extra_dialog(window, monkeypatch, tmp_path):
    window.load_demo()
    dest = tmp_path / 'meeting.docx'
    monkeypatch.setattr(ui.QFileDialog, 'getSaveFileName', lambda *args: (str(dest), ''))
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: pytest.fail('Unexpected save confirmation'))
    window.export('docx', 'Transcript')
    assert dest.stat().st_size > 500
    assert 'Saved meeting.docx' in window.status_label.text()


@pytest.mark.parametrize('error', [ConnectionRefusedError('refused'), TimeoutError('timed out'), ValueError('invalid response')])
def test_report_worker_uses_quick_notes_if_optional_writer_fails(app, monkeypatch, error):
    def broken(*args):
        raise error
    monkeypatch.setattr(ui, 'draft_ai', broken)
    session = {'title': 'Planning', 'segments': [{'start': 0, 'end': 3, 'speaker': 'Speaker', 'text': 'We agreed to launch on Friday.'}]}
    worker = ui.ReportWorker(session, 'ai', 'llama3.2')
    results, failures = [], []
    worker.done.connect(results.append)
    worker.failed.connect(failures.append)
    worker.run()
    assert not failures
    assert len(results) == 1 and results[0]['fallback']
    assert 'launch on Friday' in results[0]['minutes']
    assert 'summary' not in session  # Drafting does not mutate the original session.


def test_polished_notes_are_used_when_the_writer_works(app, monkeypatch):
    expected = {field: f'Polished {field}' for field in ('summary', 'minutes', 'memo', 'actions')}
    monkeypatch.setattr(ui, 'draft_ai', lambda *args: expected.copy())
    worker = ui.ReportWorker({'title': 'Meeting'}, 'ai', 'llama3.2')
    results = []
    worker.done.connect(results.append)
    worker.run()
    assert results == [expected]


def test_formatted_notes_round_trip_and_export_without_visible_markup(window, tmp_path):
    from docx import Document
    from solscribe.exporters import export_file
    editor = window.doc_edits['Minutes']
    editor.setMarkdown('# Meeting notes\n\n## Decisions\n\n- **Launch approved**')
    assert '# Meeting' not in editor.toPlainText()
    assert '**' not in editor.toPlainText()
    sid = window.session_id
    window.persist()
    window.load_session(sid)
    assert 'Launch approved' in window.doc_edits['Minutes'].toPlainText()
    session = window.store.get(sid)
    assert '# Meeting notes' in session['minutes']
    path = tmp_path / 'notes.docx'
    export_file(path, 'docx', session, 'Minutes')
    paragraphs = [p.text for p in Document(path).paragraphs]
    assert 'Meeting notes' in paragraphs
    assert 'Decisions' in paragraphs
    assert 'Launch approved' in paragraphs


def test_backup_restore_ui_runs_in_worker_and_recovers_notes(window, monkeypatch, tmp_path):
    window.load_demo()
    sid = window.session_id
    window.doc_edits['Summary'].setPlainText('Original notes')
    path = tmp_path / 'backup.zip'
    monkeypatch.setattr(ui.QFileDialog, 'getSaveFileName', lambda *args: (str(path), ''))
    window.backup_meetings()
    until(lambda: not window._is_busy() and path.exists())
    window.doc_edits['Summary'].setPlainText('Later edits')
    window.persist()
    monkeypatch.setattr(ui.QFileDialog, 'getOpenFileName', lambda *args: (str(path), ''))
    monkeypatch.setattr(ui.QMessageBox, 'question', lambda *args: ui.QMessageBox.Yes)
    window.restore_meetings()
    until(lambda: not window._is_busy() and window.store.get(sid)['summary'] == 'Original notes')
    assert not window.doc_edits['Summary'].isReadOnly()

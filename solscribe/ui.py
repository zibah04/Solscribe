"""SolScribe's native Windows desktop interface (Qt Widgets)."""
from __future__ import annotations

import copy
import os
import queue
import uuid
from urllib.error import URLError
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl, QSettings, QThread, Signal
from PySide6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QFrame, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLineEdit, QPushButton, QLabel, QListWidget, QListWidgetItem,
    QPlainTextEdit, QTextEdit, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QFileDialog, QMessageBox, QProgressBar, QSlider, QMenu, QCheckBox,
    QToolButton, QAbstractItemView, QInputDialog, QApplication, QSizePolicy, QScrollArea, QStackedWidget,
)

from .storage import Store
from .presentation.storage import StorageActions
from .presentation.recording import RecordingActions
from .presentation.transcripts import TranscriptActions
from .presentation.actions import ActionRegister
from .presentation.layout import WindowLayout
from .presentation.help_updates import HelpUpdates
from .presentation.study import StudyTools
from .lecture import draft_lecture, draft_lecture_ai
from .repository import timestamp
from .themes import THEMES, palette, stylesheet
from . import __version__
from .recorder import MicrophoneRecorder, SystemLoopbackRecorder
from .combined import CombinedRecorder
from .transcriber import TranscriptionWorker
from .live import LiveTranscriptionWorker
from .reports import draft_local, draft_ai, stamp, using_client
from .ollama import OllamaClient, Cancelled
from .exporters import export_file, safe_filename

SUPPORTED_AUDIO = {'.wav', '.mp3', '.m4a', '.mp4', '.mpeg', '.mpga',
                   '.aac', '.ogg', '.flac', '.webm', '.wma', '.mov'}




class ReportWorker(QThread):
    done = Signal(object)
    failed = Signal(str)
    status = Signal(str)
    cancelled = Signal()

    def __init__(self, session, method, model, parent=None):
        super().__init__(parent)
        self.session = copy.deepcopy(session)
        self.method = method
        self.model = model
        self.client = OllamaClient()
        self.result_emitted = False

    def cancel(self):
        self.client.cancel()

    def run(self):
        try:
            lecture = self.session.get('session_type') == 'lecture'
            local_draft = draft_lecture if lecture else draft_local
            ai_draft = draft_lecture_ai if lecture else draft_ai
            if self.method == 'ai':
                self.status.emit('Writing your study notes…' if lecture else 'Writing your meeting notes…')
                try:
                    with using_client(self.client):
                        output = ai_draft(self.session, self.model)
                except (OSError, ValueError, URLError) as exc:
                    self.status.emit('Making quick notes from your transcript instead…')
                    output = local_draft(self.session)
                    output['fallback'] = True
                    output['details'] = f'{type(exc).__name__}: {exc}'
            else:
                self.status.emit('Creating notes from your transcript…')
                output = local_draft(self.session)
            if self.client.cancelled.is_set():
                raise Cancelled()
            self.result_emitted = True
            self.done.emit(output)
        except Cancelled:
            self.cancelled.emit()
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')
        finally:
            self.client.release()


class MainWindow(WindowLayout, StudyTools, HelpUpdates, ActionRegister, TranscriptActions, RecordingActions, StorageActions, QMainWindow):
    def __init__(self):
        super().__init__()
        self.store = Store()
        self.settings = QSettings('SolScribe', 'SolScribe')
        self.session_id = None
        self.current_session = None
        self._loading = False
        self._worker = None
        self._report_worker = None
        self._transcription_session_id = None
        self._report_session_id = None
        self._live_worker = None
        self._live_session_id = None
        self._live_failed_message = None
        self._notes_session_id = None
        self._notes_notice = ''
        self._notes_details = ''
        self._save_error = ''
        self._storage_active = False
        self._stopping_active = False
        self._report_active = False
        self._live_active = False
        self._stop_worker = None
        self._storage_worker = None
        self._storage_restoring = False
        self._update_install_active = False
        self._closing_for_update = False
        self.recorder = MicrophoneRecorder()
        self.setWindowTitle(f'SolScribe {__version__} · Meeting notes')
        self.setMinimumSize(620, 320)
        available = self.screen().availableGeometry()
        self.resize(min(1400, max(620, available.width() - 20)),
                    min(830, max(320, available.height() - 40)))
        self._build_ui()
        self.set_theme(str(self.settings.value('theme', 'dark')))
        self._bind_shortcuts()

        self.player = QMediaPlayer(self)
        self.audio_output = QAudioOutput(self)
        self.audio_output.setVolume(.85)
        self.player.setAudioOutput(self.audio_output)
        self.player.positionChanged.connect(self._position_changed)
        self.player.durationChanged.connect(self._duration_changed)
        self.player.playbackStateChanged.connect(self._playback_changed)

        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(700)
        self.save_timer.timeout.connect(self.persist)
        self.record_timer = QTimer(self)
        self.record_timer.setInterval(180)
        self.record_timer.timeout.connect(self._refresh_recording)
        self._populate_microphones()
        for combo, key in ((self.mic_combo, 'preferred_microphone'), (self.system_combo, 'preferred_playback')):
            index = combo.findText(str(self.settings.value(key, '')))
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.currentTextChanged.connect(lambda text, key=key: self.settings.setValue(key, text))
        self.reload_library(select_id=str(self.settings.value('last_session', '')))
        if not self.session_id:
            self.new_session()
        self.statusBar().showMessage('; '.join(self.store.recovery_notices) or 'Your recordings and transcripts are stored locally.', 12000)
        self.init_help_updates()

    def set_theme(self, name):
        self.theme_name = name if name in THEMES else 'dark'
        self.settings.setValue('theme', self.theme_name)
        for combo in (self.theme_combo, self.settings_theme_combo):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(self.theme_name))
            combo.blockSignals(False)
        self.setPalette(palette(self.theme_name))
        QApplication.instance().setPalette(palette(self.theme_name))
        self.setStyleSheet(stylesheet(self.theme_name))

    def show_meeting_menu(self):
        menu = QMenu(self)
        rename = menu.addAction('Rename meeting')
        rename.triggered.connect(lambda: (self.title_edit.setFocus(), self.title_edit.selectAll()))
        menu.addSeparator()
        remove = menu.addAction('Delete meeting…')
        remove.triggered.connect(self.delete_session)
        menu.exec(self.delete_btn.mapToGlobal(self.delete_btn.rect().bottomLeft()))

    def _engine_changed(self, *args):
        self.ollama_model.setEnabled(self.engine_combo.currentData() == 'ai')

    def _show_error(self, title, message, details):
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle(title)
        dialog.setText(message)
        dialog.setDetailedText(str(details))
        dialog.exec()

    def _show_note_details(self):
        self._show_error('About these notes',
                         'Your quick notes are ready to edit and save.\n\n'
                         'The optional writing helper was unavailable, so these notes use phrases from your transcript. '
                         'You can set up the helper in Settings → Advanced writing setup, or keep using quick notes.',
                         self._notes_details)

    def _bind_shortcuts(self):
        for shortcut, fn in [('Ctrl+,', lambda: self.focus_tab(6)), ('Ctrl+N', self.new_session), ('Ctrl+O', self.import_audio),
                             ('Ctrl+S', self.persist), ('Ctrl+E', self.show_export_menu),
                             ('Ctrl+R', self.toggle_record)]:
            action = QAction(self)
            action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(fn)
            self.addAction(action)

    def _populate_microphones(self):
        self.mic_combo.clear()
        self.mic_combo.addItem('System default microphone', None)
        try:
            for device_id, name in MicrophoneRecorder.devices():
                self.mic_combo.addItem(name, device_id)
        except Exception:
            self.mic_combo.setToolTip('Mic devices unavailable; check permissions or drivers.')
        if os.name == 'nt':
            try:
                for device_id, name in SystemLoopbackRecorder.devices():
                    self.system_combo.addItem(name, device_id)
            except Exception:
                pass

    def schedule_save(self, *args):
        if not self._loading and self.session_id:
            self.save_timer.start()

    def reload_library(self, query='', select_id=None):
        selected = select_id or self.session_id
        self.library.blockSignals(True)
        self.library.clear()
        chosen_row = -1
        for index, item in enumerate(self.store.list(query)):
            label = item['title'] or 'Untitled meeting'
            if item['segments']:
                label += '  ·  transcript'
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, item['id'])
            row.setToolTip(item['title'] + '\n' + item['created_at'] + '\n' + (item['audio_path'] or 'Written notes'))
            self.library.addItem(row)
            if item['id'] == selected:
                chosen_row = index
        self.library.blockSignals(False)
        if chosen_row >= 0:
            self.library.setCurrentRow(chosen_row)
        elif self.library.count() and not query:
            self.library.setCurrentRow(0)
        if self.library.currentItem():
            chosen_id = self.library.currentItem().data(Qt.UserRole)
            if chosen_id != self.session_id or self.current_session is None:
                self.load_session(chosen_id)

    def _on_library_selected(self, current, previous):
        if current is not None:
            if self.session_id and not self.persist():
                self.library.blockSignals(True)
                for row in range(self.library.count()):
                    if self.library.item(row).data(Qt.UserRole) == self.session_id:
                        self.library.setCurrentRow(row)
                        break
                self.library.blockSignals(False)
                return
            self.load_session(current.data(Qt.UserRole))

    def load_session(self, session_id):
        session = self.store.get(session_id)
        if not session:
            return
        self.settings.setValue('last_session', session_id)
        self._loading = True
        self.session_id = session_id
        self.current_session = session
        self.mode_combo.setCurrentIndex(self.mode_combo.findData(session.get('session_type', 'meeting')))
        self.load_study(session)
        self.title_edit.setText(session['title'])
        self.title_edit.setCursorPosition(0)
        self.title_edit.setToolTip(session['title'])
        self.date_edit.setText(session['meeting_date'])
        self.attendees_edit.setText(session['attendees'])
        self.location_edit.setText(session['location'])
        self.chair_edit.setText(session['chair'])
        self.agenda_edit.setText(session['agenda'])
        self.table.blockSignals(True)
        self.table.setUpdatesEnabled(False)
        self.table.setRowCount(len(session['segments']))
        for idx, segment in enumerate(session['segments']):
            start = QTableWidgetItem(stamp(segment.get('start', 0)))
            start.setFlags(start.flags() & ~Qt.ItemIsEditable)
            start.setData(Qt.UserRole, float(segment.get('start') or 0))
            start.setData(Qt.UserRole + 1, float(segment.get('end') or 0))
            self.table.setItem(idx, 0, start)
            self.table.setItem(idx, 1, QTableWidgetItem(segment.get('speaker') or 'Speaker'))
            self.table.setItem(idx, 2, QTableWidgetItem(segment.get('text') or ''))
        self.table.blockSignals(False)
        self.table.setUpdatesEnabled(True)
        self.resize_visible_rows()
        self.search_transcript.clear()
        self.caption_status.setText('Your words are saved · create notes or start a new recording' if session['segments'] else 'Your transcript will appear below')
        for name, field in [('Summary', 'summary'), ('Minutes', 'minutes'), ('Memo', 'memo'), ('Action items', 'actions')]:
            self.doc_edits[name].setMarkdown(session.get(field) or '')
        self.load_actions(session.get('action_items', []))
        for checkbox in self.review_checks:
            checkbox.blockSignals(True)
            checkbox.setChecked(bool(session.get('reviewed_at')))
            checkbox.blockSignals(False)
        path = session.get('audio_path')
        self.playback_controls.setVisible(bool(path and Path(path).is_file()))
        if path and Path(path).is_file():
            self.audio_name.setText(Path(path).name)
            self.audio_name.setToolTip(str(path))
            self.player.setSource(QUrl.fromLocalFile(str(Path(path).resolve())))
            self.play_btn.setEnabled(True)
        else:
            self.audio_name.setText('Recording not found' if path else 'Written notes · no recording attached' if session['segments'] else 'No recording yet')
            self.audio_name.setToolTip(str(path or ''))
            self.player.setSource(QUrl())
            self.play_btn.setEnabled(False)
        self.audio_length.setText(stamp(session.get('duration') or 0))
        self._loading = False
        self.apply_session_type()
        self.status_label.setText('Saved on this PC · changes save automatically')

    def update_actions(self):
        has_audio = bool(self.current_session and self.current_session.get('audio_path') and
                         Path(self.current_session['audio_path']).is_file())
        transcribing = bool(self._worker and self._worker.isRunning())
        live_working = self._live_active or bool(self._live_worker and self._live_worker.isRunning())
        reporting = self._report_active or bool(self._report_worker and self._report_worker.isRunning())
        recording = self.record_timer.isActive()
        storage_busy = self._storage_active or self._update_install_active or bool(self._storage_worker and self._storage_worker.isRunning())
        stopping = self._stopping_active or bool(self._stop_worker and self._stop_worker.isRunning())
        busy = transcribing or reporting or live_working or storage_busy or stopping
        self.mode_combo.setEnabled(not busy and not recording)
        self.study_edit.setReadOnly(reporting or storage_busy)
        self.study_tabs.widget(1).setEnabled(not reporting and not storage_busy)
        self.guide_btn.setEnabled(not busy and not recording)
        self.settings_guide_btn.setEnabled(not busy and not recording)
        has_words = bool(self.current_session and self.current_session.get('segments'))
        self.transcript_stack.setCurrentIndex(0 if self.table.rowCount() else 1)
        if recording or live_working:
            self.empty_title.setText('Your words will appear here.')
            self.empty_hint.setText('Keep speaking naturally. First use may need a speech download; your recording is being saved.')
        elif has_audio:
            self.empty_title.setText('Your recording is ready.')
            self.empty_hint.setText('Choose Create transcript to turn the recording into words you can review and edit.')
        else:
            self.empty_title.setText('Capture a lecture, one idea at a time.' if self.session_type() == 'lecture' else 'Every meeting, clearly captured.')
            self.empty_hint.setText('Record a conversation, add an audio or video file, or paste notes to get started.')
        for control in (self.capture_mode, self.system_combo, self.mic_combo, self.live_checkbox, self.live_model_combo, self.language_combo):
            control.setEnabled(not recording and not live_working)
        self.transcribe_btn.setEnabled((has_audio and not reporting and not recording and not live_working) or transcribing)
        if not transcribing:
            self.transcribe_btn.setText('Improve transcript' if has_words and has_audio else 'Create transcript')
        self.record_btn.setEnabled(not stopping and not storage_busy)
        self.action_table.setEnabled(not reporting and not storage_busy)
        for checkbox in self.review_checks:
            checkbox.setEnabled(not busy)
        self.speakers_btn.setEnabled(has_words and not busy and not recording)
        self.report_btn.setEnabled(has_words and not busy and not recording)
        self.export_btn.setEnabled(bool(has_words or self.action_table.rowCount() or any(edit.toPlainText().strip() for edit in self.doc_edits.values())) and not recording and not busy)
        self.cancel_report_btn.setVisible(reporting and not self._report_worker.result_emitted)
        for edit in self.doc_edits.values():
            edit.setReadOnly(reporting or storage_busy)
        has_notice = self.session_id == self._notes_session_id and bool(self._notes_notice)
        self.notes_details_btn.setVisible(has_notice and not busy and not recording)
        if storage_busy:
            hint = 'Working on your backup. Please keep this window open…'
        elif recording:
            hint = 'Your recording is being saved. Your words appear below.' if self.live_checkbox.isChecked() else 'Your recording is being saved. Click Stop recording when finished.'
        elif transcribing:
            hint = 'Turning your recording into text…'
        elif reporting:
            hint = 'Creating your notes… you can edit them when they are ready.'
        elif live_working:
            hint = 'Finishing the last words from your recording…'
        elif has_notice:
            hint = self._notes_notice
        elif has_words:
            hint = 'Your transcript is ready. Create notes or save a copy.'
        elif has_audio:
            hint = 'Next: click Create transcript to see the words in your recording.'
        else:
            hint = 'Record or add a recording to begin.'
        if self._save_error:
            hint = 'Changes are not saved yet. Check available disk space and try again.'
        self.flow_hint.setText(hint)
        self.delete_btn.setEnabled(not busy and not recording)
        for control in (self.title_edit, self.table, self.date_edit, self.attendees_edit, self.location_edit, self.chair_edit, self.agenda_edit):
            control.setEnabled(not storage_busy)
        for control in (self.new_btn, self.import_btn, self.paste_btn, self.demo_btn,
                        self.library, self.search_library):
            control.setEnabled(not busy and not recording)
        for compact, original in self.compact_controls:
            compact.setEnabled(original.isEnabled())
        self.compact_record.setText(self.record_btn.text())
        self.compact_record.setEnabled(self.record_btn.isEnabled())
        self.compact_record.setObjectName(self.record_btn.objectName())
        self.compact_record.style().unpolish(self.compact_record)
        self.compact_record.style().polish(self.compact_record)

    def _is_busy(self):
        return bool(self._update_install_active or self._storage_active or self._stopping_active or self._report_active or self._live_active or (self._stop_worker and self._stop_worker.isRunning()) or
                    (self._storage_worker and self._storage_worker.isRunning()) or
                    (self._worker and self._worker.isRunning()) or
                    (self._report_worker and self._report_worker.isRunning()) or
                    (self._live_worker and self._live_worker.isRunning()))

    def new_session(self):
        if self._is_busy():
            return
        if self.record_timer.isActive():
            QMessageBox.warning(self, 'Recording in progress', 'Stop the recording before creating another session.')
            return
        if not self.persist():
            return
        mode = self.session_type() if self.session_id else str(self.settings.value('new_session_type', 'meeting'))
        session_id = self.store.create('Untitled lecture' if mode == 'lecture' else 'Untitled meeting', session_type=mode)
        self.search_library.clear()
        self.reload_library(select_id=session_id)
        self.focus_tab(0)
        self.title_edit.setFocus()
        self.title_edit.selectAll()
        return session_id

    def load_demo(self):
        if self._is_busy():
            return
        if self.record_timer.isActive():
            return
        if not self.persist():
            return
        session_id = self.store.demo_lecture() if self.session_type() == 'lecture' else self.store.demo()
        self.search_library.clear()
        self.reload_library(select_id=session_id)
        self.caption_status.setText('Example lecture · saved sample text, not live audio.' if self.session_type() == 'lecture' else 'Example meeting · sample text. Click Record meeting to capture your own words.')
        self.statusBar().showMessage('Example lecture loaded. Try Create study notes.' if self.session_type() == 'lecture' else 'Example meeting loaded. Try Create notes.', 8000)

    def import_audio(self, path=None):
        if self._is_busy():
            return
        if self.record_timer.isActive():
            QMessageBox.warning(self, 'Recording in progress', 'Stop the recording before importing audio.')
            return
        if not isinstance(path, (str, Path)):
            path, _ = QFileDialog.getOpenFileName(self, 'Import recording / audio / video',
                str(Path.home()), 'Audio and video (*.wav *.mp3 *.m4a *.mp4 *.mpeg *.mpga *.aac *.ogg *.flac *.webm *.wma *.mov);;All files (*.*)')
        if not path:
            return
        path = Path(path)
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_AUDIO:
            QMessageBox.warning(self, 'Unsupported file', 'Choose a supported audio or video recording.')
            return
        if not self.persist():
            return
        session_id = self.store.create(path.stem.replace('_', ' '), str(path.resolve()), session_type=self.session_type())
        self.search_library.clear()
        self.reload_library(select_id=session_id)
        self.status_label.setText('Ready to transcribe. Files stay in their original location.')
        self.statusBar().showMessage('Recording added. Click Create transcript to see the words.', 9000)

    def paste_text(self):
        if self._is_busy():
            return
        if self.record_timer.isActive():
            return
        content, ok = QInputDialog.getMultiLineText(self, 'Paste existing words / notes',
                            'Paste a transcript or notes here:')
        if not ok or not content.strip():
            return
        if not self.persist():
            return
        session_id = self.store.create('Pasted lecture' if self.session_type() == 'lecture' else 'Pasted meeting notes', session_type=self.session_type())
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        segments = [{'start': 0, 'end': 0, 'speaker': 'Written notes', 'text': line} for line in lines]
        self.store.update(session_id, segments=segments, model='pasted text')
        self.search_library.clear()
        self.reload_library(select_id=session_id)

    def transcribe(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.transcribe_btn.setText('Cancelling…')
            self.transcribe_btn.setEnabled(False)
            self.status_label.setText('Cancellation requested; waiting for the current segment…')
            return
        if not self.current_session or not self.current_session.get('audio_path'):
            return
        if not self.persist():
            return
        self._transcription_session_id = self.session_id
        self._worker = TranscriptionWorker(self.current_session['audio_path'],
                    self.model_combo.currentData(), self.language_combo.currentData(),
                    self.store.models, self)
        self._worker.status.connect(self._work_status)
        self._worker.progress.connect(self._progress_changed)
        self._worker.result.connect(self._transcribed)
        self._worker.failed.connect(self._task_failed)
        self._worker.finished.connect(self._transcription_finished)
        self.progress.setRange(0, 0)
        self.progress.show()
        self._worker.start()
        self.transcribe_btn.setText('■  Cancel transcription')
        self.update_actions()

    def _work_status(self, message):
        self.status_label.setText(message)
        self.statusBar().showMessage(message)

    def _progress_changed(self, value):
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self.progress.setValue(value)

    def _transcription_finished(self):
        self.progress.hide()
        self.transcribe_btn.setText('Create transcript')
        self.update_actions()

    def generate_reports(self):
        if self._is_busy() or self.record_timer.isActive():
            return
        if not self.persist():
            return
        session = self.store.get(self.session_id) if self.session_id else None
        if not session:
            return
        if not session['segments']:
            QMessageBox.information(self, 'Transcript needed',
                                   'Record or import audio and transcribe it, or paste meeting notes first.')
            return
        fields = ('study_notes', 'study_items') if session.get('session_type') == 'lecture' else ('summary', 'minutes', 'memo', 'actions')
        if any(session.get(k) for k in fields):
            answer = QMessageBox.question(self, 'Replace current documents?',
                'Create fresh notes and replace your current edits? Your transcript will be kept.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if answer != QMessageBox.Yes:
                return
        method = self.engine_combo.currentData()
        model = self.ollama_model.text().strip() or 'llama3.2'
        self._notes_notice = ''
        self._notes_details = ''
        self._notes_session_id = self.session_id
        self._report_session_id = self.session_id
        self._report_active = True
        self._report_worker = ReportWorker(session, method, model, self)
        self._report_worker.status.connect(self._work_status)
        self._report_worker.done.connect(self._reports_ready)
        self._report_worker.failed.connect(self._report_failed)
        self._report_worker.cancelled.connect(lambda: self.status_label.setText('Writing cancelled. Your existing notes are kept.'))
        self._report_worker.finished.connect(self._report_finished)
        self.progress.setRange(0, 0)
        self.progress.show()
        self._report_worker.start()
        self.update_actions()

    def _report_finished(self):
        self._report_active = False
        self.update_actions()

    def _reports_ready(self, output):
        self.progress.hide()
        target_id = self._report_session_id
        lecture = 'study_notes' in output
        if lecture:
            self.store.update(target_id, study_notes=output['study_notes'], study_items=output['study_items'],
                              study_source_hash=output['study_source_hash'], study_warnings=output.get('warnings', []))
        else:
            self.store.update(target_id, summary=output['summary'], minutes=output['minutes'],
                          memo=output['memo'], actions=output['actions'], action_items=output.get('action_items', []),
                          notes_warnings=output.get('warnings', []), reviewed_at='')
        if self.session_id == target_id:
            self.load_session(target_id)
        self.focus_tab(7 if lecture else 1)
        if output.get('fallback'):
            self._notes_notice = 'Quick notes are ready. The optional writing helper is unavailable.'
            self._notes_details = output.get('details', '')
        else:
            self._notes_notice = ''
            self._notes_details = ''
        self.status_label.setText('✓ Your notes are ready. Edit anything, then save a copy.')
        self.statusBar().showMessage('Study notes and revision cards saved.' if lecture else 'Summary, minutes, memo and action list saved.', 9000)
        self.update_actions()

    def _report_failed(self, message):
        self.progress.hide()
        self._show_error('Could not create notes',
                         'Your transcript and saved notes are safe. Please try again.', message)
        self.status_label.setText('Could not create notes. Your saved work is safe.')

    def _task_failed(self, message):
        self.progress.hide()
        self._show_error('Could not read this recording',
                         'Your recording is safe. Check that it plays correctly and that you are online for the first speech download, then try again.', message)
        self.status_label.setText('Could not create a transcript. Your recording is safe.')

    def _segment_clicked(self, row, column):
        if column == 0 and self.table.item(row, 0):
            milliseconds = int(float(self.table.item(row, 0).data(Qt.UserRole) or 0) * 1000)
            if self.current_session and self.current_session.get('audio_path'):
                self.player.setPosition(milliseconds)
                self.player.play()

    def resize_visible_rows(self, *args):
        if getattr(self, '_sizing_rows', False) or not self.table.rowCount():
            return
        self._sizing_rows = True
        try:
            first = max(0, self.table.rowAt(0))
            last = self.table.rowAt(self.table.viewport().height() - 1)
            last = last if last >= first else first + 24
            for row in range(first, min(last + 2, first + 50, self.table.rowCount())):
                self.table.resizeRowToContents(row)
        finally:
            self._sizing_rows = False

    def filter_transcript(self, query):
        for row in range(self.table.rowCount()):
            speaker = self.table.item(row, 1).text() if self.table.item(row, 1) else ''
            text = self.table.item(row, 2).text() if self.table.item(row, 2) else ''
            self.table.setRowHidden(row, bool(query and query.lower() not in (speaker + ' ' + text).lower()))

    def persist(self):
        if self._loading or not self.session_id:
            return True
        self.save_timer.stop()
        segments = []
        for row in range(self.table.rowCount()):
            # The table cells are authoritative for live captions. Looking up
            # the previous saved row here lost timestamps for newly appended
            # live segments (and could make every timestamp zero).
            clock = self.table.item(row, 0)
            segments.append({'start': float(clock.data(Qt.UserRole) or 0) if clock else 0.0,
                             'end': float(clock.data(Qt.UserRole + 1) or 0) if clock else 0.0,
                             'speaker': self.table.item(row, 1).text() if self.table.item(row, 1) else 'Speaker',
                             'text': self.table.item(row, 2).text() if self.table.item(row, 2) else ''})
        new_title = self.title_edit.text().strip() or ('Untitled lecture' if self.session_type() == 'lecture' else 'Untitled meeting')
        try:
            self.store.update(self.session_id, title=new_title, segments=segments,
                              session_type=self.session_type(), study_notes=self.study_edit.toMarkdown().strip(), study_items=self.study_items,
                              meeting_date=self.date_edit.text().strip(),
                              attendees=self.attendees_edit.text().strip(),
                              location=self.location_edit.text().strip(),
                              chair=self.chair_edit.text().strip(),
                              agenda=self.agenda_edit.text().strip(),
                              summary=self.doc_edits['Summary'].toMarkdown().strip(),
                              minutes=self.doc_edits['Minutes'].toMarkdown().strip(),
                              memo=self.doc_edits['Memo'].toMarkdown().strip(),
                              actions=self.doc_edits['Action items'].toMarkdown().strip(),
                              action_items=self.action_values(),
                              reviewed_at=(self.current_session.get('reviewed_at') or timestamp()) if self.review_checks[0].isChecked() else '')
            self.current_session = self.store.get(self.session_id)
            self.refresh_study_notice(self.current_session)
        except Exception as exc:
            self._save_error = str(exc)
            self.status_label.setText('Changes are not saved yet. Check available disk space and try again.')
            self.update_actions()
            return False
        had_error = bool(self._save_error)
        self._save_error = ''
        if had_error:
            self.status_label.setText('Your changes are saved.')
            self.update_actions()
        active = self.library.currentItem()
        if active and active.data(Qt.UserRole) == self.session_id:
            active.setText(new_title + ('  ·  transcript' if segments else ''))
        self.update_actions()
        return True

    def current_section(self):
        if self.tabs.currentIndex() == 7:
            return ('Study notes', 'Revision cards', 'Study sources')[self.study_tabs.currentIndex()]
        if self.tabs.currentIndex() == 4 and self.action_tabs.currentIndex() == 0:
            return 'Action register'
        return {0: 'Transcript', 1: 'Summary', 2: 'Minutes', 3: 'Memo', 4: 'Action items'}.get(self.tabs.currentIndex(), 'Transcript')

    def show_export_menu(self):
        if not self.export_btn.isEnabled():
            return
        menu = QMenu(self)
        section = self.current_section()
        for format_name, suffix in [('Word document', 'docx'), ('PDF', 'pdf'), ('Text file', 'txt')]:
            action = menu.addAction(f'Save {section.lower()} as {format_name}')
            action.triggered.connect(lambda checked=False, ext=suffix, sec=section: self.export(ext, sec))
        more = menu.addMenu('More formats')
        action = more.addAction('Markdown (.md)')
        action.triggered.connect(lambda: self.export('md', section))
        action = more.addAction('Subtitles (.srt)')
        action.triggered.connect(lambda checked=False: self.export('srt', 'Transcript'))
        action = more.addAction('All recording data (.json)')
        action.triggered.connect(lambda checked=False: self.export('json', 'Transcript'))
        menu.exec(self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft()))

    def export(self, extension, section):
        if not self.session_id:
            return
        if not self.persist():
            return
        session = self.store.get(self.session_id)
        name = safe_filename(session['title'])
        suffix = safe_filename(section).replace(' ', '-')
        filename = f'{name} - {suffix}.{extension}' if extension != 'json' else f'{name} - project.json'
        documents = Path.home() / 'Documents'
        if not documents.exists():
            documents = Path.home()
        destination, _ = QFileDialog.getSaveFileName(self, 'Save a copy',
                        str(documents / filename), f'{extension.upper()} files (*.{extension})')
        if not destination:
            return
        try:
            output = export_file(destination, extension, session, section)
            self.statusBar().showMessage(f'Saved a copy: {output}', 10000)
            self.status_label.setText(f'✓ Saved {output.name}')
        except Exception as exc:
            self._show_error('Could not save a copy',
                             'Your work is still saved in SolScribe. Try another folder, or close the destination file and try again.', exc)

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def player_seek(self, position):
        self.player.setPosition(position)

    def _position_changed(self, ms):
        if not self.seek.isSliderDown():
            self.seek.setValue(int(ms))
        self.audio_position.setText(stamp(ms / 1000))

    def _duration_changed(self, ms):
        self.seek.setRange(0, ms)
        self.audio_length.setText(stamp(ms / 1000))

    def _playback_changed(self, state):
        self.play_btn.setText('Pause' if state == QMediaPlayer.PlayingState else 'Play')

    def dragEnterEvent(self, event):
        files = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(u.isLocalFile() and Path(u.toLocalFile()).suffix.lower() in SUPPORTED_AUDIO for u in files):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED_AUDIO:
                self.import_audio(url.toLocalFile())
                event.acceptProposedAction()
                break

    def closeEvent(self, event):
        if self._closing_for_update:
            self._update_auto_timer.stop()
            event.accept()
            return
        if self._update_install_active:
            self.statusBar().showMessage('Preparing the update. SolScribe will close when it is ready.', 6000)
            event.ignore()
            return
        if self.record_timer.isActive():
            response = QMessageBox.question(self, 'Recording still active',
                                            'Stop the recording and close SolScribe?',
                                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if response != QMessageBox.Yes:
                event.ignore()
                return
            self.toggle_record()
        if self._is_busy():
            QMessageBox.information(self, 'Please finish current task',
                                   'A task is still finishing. Please close the app after it completes.')
            event.ignore()
            return
        if not self.persist():
            self._show_error('Your changes are not saved yet',
                             'Please check available disk space and try again. Keep this window open to protect your edits.',
                             self._save_error)
            event.ignore()
            return
        self._update_auto_timer.stop()
        self._update_client.cancel()
        if self._guide is not None:
            self._guide.reject()
        if self._update_dialog is not None:
            self._update_dialog.reject()
        event.accept()

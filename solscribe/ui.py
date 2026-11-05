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
from .themes import THEMES, palette, stylesheet
from . import __version__
from .recorder import MicrophoneRecorder, SystemLoopbackRecorder
from .combined import CombinedRecorder
from .transcriber import TranscriptionWorker
from .live import LiveTranscriptionWorker
from .reports import draft_local, draft_ai, stamp
from .exporters import export_file, safe_filename

SUPPORTED_AUDIO = {'.wav', '.mp3', '.m4a', '.mp4', '.mpeg', '.mpga',
                   '.aac', '.ogg', '.flac', '.webm', '.wma', '.mov'}




class ReportWorker(QThread):
    done = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, session, method, model, parent=None):
        super().__init__(parent)
        self.session = copy.deepcopy(session)
        self.method = method
        self.model = model

    def run(self):
        try:
            if self.method == 'ai':
                self.status.emit('Writing your meeting notes…')
                try:
                    output = draft_ai(self.session, self.model)
                except (OSError, ValueError, URLError) as exc:
                    self.status.emit('Making quick notes from your transcript instead…')
                    output = draft_local(self.session)
                    output['fallback'] = True
                    output['details'] = f'{type(exc).__name__}: {exc}'
            else:
                self.status.emit('Creating notes from your transcript…')
                output = draft_local(self.session)
            self.done.emit(output)
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')


class MainWindow(TranscriptActions, RecordingActions, StorageActions, QMainWindow):
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
        self._stop_worker = None
        self._storage_worker = None
        self._storage_restoring = False
        self.recorder = MicrophoneRecorder()
        self.setWindowTitle(f'SolScribe {__version__} · Meeting notes')
        self.setMinimumSize(1000, 640)
        available = self.screen().availableGeometry()
        self.resize(min(1400, max(1000, available.width() - 40)),
                    min(830, max(640, available.height() - 60)))
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
        self.reload_library(select_id=str(self.settings.value('last_session', '')))
        if not self.session_id:
            self.new_session()
        self.statusBar().showMessage('; '.join(self.store.recovery_notices) or 'Your recordings and transcripts are stored locally.', 12000)

    @staticmethod
    def _label(text, role='Muted'):
        w = QLabel(text)
        w.setObjectName(role)
        return w

    @staticmethod
    def _button(text, role=None):
        w = QPushButton(text)
        if role:
            w.setObjectName(role)
        w.setCursor(Qt.PointingHandCursor)
        return w

    def _build_ui(self):
        base = QWidget()
        base.setObjectName('AppRoot')
        self.setCentralWidget(base)
        outer = QHBoxLayout(base)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        side = QFrame()
        side.setObjectName('Sidebar')
        side.setFixedWidth(236)
        outer.addWidget(side)
        sidebar = QVBoxLayout(side)
        sidebar.setContentsMargins(14, 18, 14, 14)
        sidebar.setSpacing(9)

        brand_row = QHBoxLayout()
        brand_row.setSpacing(12)
        logo = QLabel('S')
        logo.setObjectName('LogoIcon')
        logo.setFixedSize(47, 47)
        logo.setAlignment(Qt.AlignCenter)
        brand_row.addWidget(logo)
        brand_col = QVBoxLayout()
        brand_col.setSpacing(1)
        brand_col.addWidget(self._label('SolScribe', 'Brand'))
        brand_col.addWidget(self._label('MEETING STUDIO', 'BrandTag'))
        brand_row.addLayout(brand_col)
        brand_row.addStretch(1)
        sidebar.addLayout(brand_row)
        sidebar.addSpacing(13)
        self.new_btn = self._button('New meeting', 'Primary')
        self.new_btn.clicked.connect(self.new_session)
        sidebar.addWidget(self.new_btn)
        self.import_btn = self._button('Add a recording', 'Plain')
        self.import_btn.clicked.connect(self.import_audio)
        sidebar.addWidget(self.import_btn)
        self.record_btn = self._button('Record meeting', 'Record')
        self.record_btn.clicked.connect(self.toggle_record)
        sidebar.addWidget(self.record_btn)
        self.paste_btn = self._button('Paste text', 'Plain')
        self.paste_btn.clicked.connect(self.paste_text)
        sidebar.addWidget(self.paste_btn)
        sidebar.addSpacing(8)
        sidebar.addWidget(self._label('YOUR MEETINGS', 'Eyebrow'))
        self.search_library = QLineEdit()
        self.search_library.setPlaceholderText('Search meeting titles…')
        self.search_library.textChanged.connect(lambda value: self.reload_library(query=value))
        sidebar.addWidget(self.search_library)
        self.library = QListWidget()
        self.library.setTextElideMode(Qt.ElideRight)
        self.library.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.library.currentItemChanged.connect(self._on_library_selected)
        sidebar.addWidget(self.library, 1)
        self.demo_btn = self._button('Example meeting', 'Plain')
        self.demo_btn.setToolTip('Opens a saved sample transcript, not a live microphone demo.')
        self.demo_btn.clicked.connect(self.load_demo)
        sidebar.addWidget(self.demo_btn)
        self.folder_btn = self._button('Open saved files', 'Plain')
        self.folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root))))
        sidebar.addWidget(self.folder_btn)
        theme_row = QHBoxLayout()
        theme_label = self._label('Appearance', 'Hint')
        theme_row.addWidget(theme_label)
        self.theme_combo = QComboBox()
        self.theme_combo.addItem('Dark', 'dark')
        self.theme_combo.addItem('Light', 'light')
        self.theme_combo.setAccessibleName('Appearance')
        theme_label.setBuddy(self.theme_combo)
        self.theme_combo.currentIndexChanged.connect(lambda _: self.set_theme(self.theme_combo.currentData()))
        theme_row.addWidget(self.theme_combo, 1)
        sidebar.addLayout(theme_row)
        sidebar.addWidget(self._label('Private · saved on this PC', 'Hint'))

        content = QWidget()
        outer.addWidget(content, 1)
        work = QVBoxLayout(content)
        work.setContentsMargins(18, 14, 18, 12)
        work.setSpacing(10)

        header = QHBoxLayout()
        title_stack = QVBoxLayout()
        title_stack.setSpacing(3)
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName('TitleInput')
        self.title_edit.setPlaceholderText('Name this meeting…')
        self.title_edit.textChanged.connect(self.schedule_save)
        title_stack.addWidget(self.title_edit)
        header.addLayout(title_stack, 1)
        self.delete_btn = self._button('More', 'Plain')
        self.delete_btn.setAccessibleName('Meeting options')
        self.delete_btn.clicked.connect(self.show_meeting_menu)
        header.addWidget(self.delete_btn)
        self.export_btn = self._button('Save a copy', 'Plain')
        self.export_btn.clicked.connect(self.show_export_menu)
        header.addWidget(self.export_btn)
        work.addLayout(header)

        audio_box = QFrame()
        audio_box.setObjectName('Panel')
        a_layout = QVBoxLayout(audio_box)
        a_layout.setContentsMargins(12, 10, 12, 10)
        a_layout.setSpacing(6)
        audio_row = QHBoxLayout()
        left_audio = QVBoxLayout()
        left_audio.setSpacing(4)
        self.audio_name = QLabel('No recording yet · record a meeting or add a file')
        self.audio_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.audio_name.setMinimumWidth(0)
        left_audio.addWidget(self.audio_name)
        audio_row.addLayout(left_audio, 1)
        self.play_btn = self._button('Play', 'Small')
        self.play_btn.clicked.connect(self.toggle_play)
        audio_row.addWidget(self.play_btn)
        a_layout.addLayout(audio_row)
        self.playback_controls = QWidget()
        playback = QHBoxLayout(self.playback_controls)
        playback.setContentsMargins(0, 0, 0, 0)
        playback.setSpacing(10)
        self.audio_position = self._label('00:00', 'Muted')
        playback.addWidget(self.audio_position)
        self.seek = QSlider(Qt.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(self.player_seek)
        playback.addWidget(self.seek, 1)
        self.audio_length = self._label('00:00', 'Muted')
        playback.addWidget(self.audio_length)
        a_layout.addWidget(self.playback_controls)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(self._label('Recording quality', 'SettingLabel'))
        self.model_combo = QComboBox()
        for label, model in [('Balanced', 'base'), ('More accurate', 'small'), ('Fastest', 'tiny'),
                             ('High accuracy · slower', 'medium'), ('Highest accuracy · slowest', 'large-v3')]:
            self.model_combo.addItem(label, model)
        self.model_combo.setToolTip('Choose faster results or greater accuracy when creating a transcript from a recording.')
        self.model_combo.setCurrentIndex(max(0, self.model_combo.findData(str(self.settings.value('whisper_model', 'base')))))
        self.model_combo.currentIndexChanged.connect(lambda _: self.settings.setValue('whisper_model', self.model_combo.currentData()))
        controls.addWidget(self.model_combo)
        controls.addWidget(self._label('Language', 'SettingLabel'))
        self.language_combo = QComboBox()
        for label, code in [('Auto detect', 'auto'), ('English', 'en'), ('French', 'fr'),
                            ('Spanish', 'es'), ('Portuguese', 'pt'), ('German', 'de'),
                            ('Arabic', 'ar'), ('Yoruba', 'yo'), ('Hausa', 'ha')]:
            self.language_combo.addItem(label, code)
        for i in range(self.language_combo.count()):
            if self.language_combo.itemData(i) == self.settings.value('language', 'auto'):
                self.language_combo.setCurrentIndex(i)
                break
        self.language_combo.currentIndexChanged.connect(
            lambda _: self.settings.setValue('language', self.language_combo.currentData()))
        controls.addWidget(self.language_combo)
        controls.addStretch(1)
        self.transcribe_btn = self._button('Create transcript', 'Primary')
        self.transcribe_btn.clicked.connect(self.transcribe)
        audio_row.addWidget(self.transcribe_btn)
        live_row = QHBoxLayout()
        self.live_checkbox = QCheckBox('Show words while I speak')
        self.live_checkbox.setChecked(self.settings.value('live_captions', True, type=bool))
        self.live_checkbox.setToolTip('Your words appear below after a short pause. You can improve the transcript after recording.')
        self.live_checkbox.toggled.connect(self._live_option_changed)
        live_row.addWidget(self.live_checkbox)
        live_row.addStretch(1)
        live_controls = QHBoxLayout()
        live_controls.addWidget(self._label('While recording', 'SettingLabel'))
        self.live_model_combo = QComboBox()
        for label, model in [('Fast captions', 'tiny'), ('Balanced captions', 'base'), ('More accurate · slower', 'small')]:
            self.live_model_combo.addItem(label, model)
        self.live_model_combo.setCurrentIndex(max(0, self.live_model_combo.findData(str(self.settings.value('live_model', 'tiny')))))
        self.live_model_combo.setToolTip('Fast captions are recommended so your words appear sooner.')
        self.live_model_combo.currentIndexChanged.connect(lambda _: self.settings.setValue('live_model', self.live_model_combo.currentData()))
        live_controls.addWidget(self.live_model_combo)
        live_controls.addStretch(1)
        a_layout.addLayout(live_row)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(7)
        self.progress.hide()
        a_layout.addWidget(self.progress)
        self.status_label = self._label('Ready', 'Hint')
        a_layout.addWidget(self.status_label)
        work.addWidget(audio_box)

        details_box = QFrame()
        details_box.setObjectName('SettingPanel')
        details = QGridLayout(details_box)
        details.setContentsMargins(16, 13, 16, 14)
        details.setHorizontalSpacing(13)
        details.setVerticalSpacing(5)
        self.date_edit = QLineEdit()
        self.date_edit.setPlaceholderText('YYYY-MM-DD')
        self.attendees_edit = QLineEdit()
        self.attendees_edit.setPlaceholderText('People present…')
        self.location_edit = QLineEdit()
        self.location_edit.setPlaceholderText('Meeting room / online')
        self.chair_edit = QLineEdit()
        self.chair_edit.setPlaceholderText('Chairperson…')
        self.agenda_edit = QLineEdit()
        self.agenda_edit.setPlaceholderText('Topics covered in the meeting…')
        entries = [('MEETING DATE', self.date_edit), ('ATTENDEES', self.attendees_edit),
                   ('LOCATION', self.location_edit), ('CHAIR', self.chair_edit)]
        for index, (label, edit) in enumerate(entries):
            details.addWidget(self._label(label, 'SettingLabel'), 0, index)
            details.addWidget(edit, 1, index)
            edit.textChanged.connect(self.schedule_save)
        details.addWidget(self._label('AGENDA', 'SettingLabel'), 2, 0)
        details.addWidget(self.agenda_edit, 2, 1, 1, 3)
        self.agenda_edit.textChanged.connect(self.schedule_save)

        report_row = QHBoxLayout()
        self.flow_hint = self._label('Record a meeting or add a recording to begin.', 'Hint')
        self.flow_hint.setWordWrap(True)
        report_row.addWidget(self.flow_hint, 1)
        writing_controls = QHBoxLayout()
        writing_controls.addWidget(self._label('Note style', 'SettingLabel'))
        self.engine_combo = QComboBox()
        self.engine_combo.addItem('Quick notes · ready to use', 'local')
        self.engine_combo.addItem('Polished notes · optional helper', 'ai')
        self.engine_combo.setCurrentIndex(0 if self.settings.value('engine', 'local') == 'local' else 1)
        self.engine_combo.currentIndexChanged.connect(
            lambda _: self.settings.setValue('engine', self.engine_combo.currentData()))
        writing_controls.addWidget(self.engine_combo)
        writing_controls.addStretch(1)
        self.ollama_model = QLineEdit(str(self.settings.value('ollama_model', 'llama3.2')))
        self.ollama_model.setFixedWidth(125)
        self.ollama_model.setToolTip('Ollama local model name. Example: llama3.2')
        self.ollama_model.textChanged.connect(lambda v: self.settings.setValue('ollama_model', v))
        self.notes_details_btn = self._button('Why quick notes?', 'Plain')
        self.notes_details_btn.clicked.connect(self._show_note_details)
        self.notes_details_btn.hide()
        report_row.addWidget(self.notes_details_btn)
        self.report_btn = self._button('Create notes', 'Primary')
        self.report_btn.setToolTip('Create a summary, minutes, memo and action list. You can edit everything afterward.')
        self.report_btn.clicked.connect(self.generate_reports)
        report_row.addWidget(self.report_btn)
        work.addLayout(report_row)
        self.engine_combo.currentIndexChanged.connect(self._engine_changed)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setMinimumHeight(270)
        self.tabs.setUsesScrollButtons(True)
        transcript_tab = QWidget()
        t_layout = QVBoxLayout(transcript_tab)
        t_layout.setContentsMargins(10, 10, 10, 10)
        t_layout.setSpacing(10)
        transcript_head = QHBoxLayout()
        self.caption_status = self._label('Ready · choose a microphone, then click Record meeting', 'Hint')
        self.caption_status.setWordWrap(True)
        self.caption_status.setMinimumHeight(32)
        transcript_head.addWidget(self.caption_status, 1)
        self.search_transcript = QLineEdit()
        self.search_transcript.setPlaceholderText('Find in transcript…')
        self.search_transcript.setMaximumWidth(240)
        self.search_transcript.textChanged.connect(self.filter_transcript)
        transcript_head.addWidget(self.search_transcript)
        self.speakers_btn = self._button('Speakers', 'Plain')
        self.speakers_btn.clicked.connect(self.rename_speakers)
        transcript_head.addWidget(self.speakers_btn)
        t_layout.addLayout(transcript_head)
        self.table = QTableWidget(0, 3)
        self.table.setToolTip('Double-click words or speakers to edit. Click a timestamp to play source audio.')
        self.table.setHorizontalHeaderLabels(['TIME', 'SPEAKER', 'TRANSCRIPT · double-click to edit'])
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed)
        self.table.setWordWrap(True)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(49)
        self.table.verticalHeader().setMinimumSectionSize(48)
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setMinimumHeight(160)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.setColumnWidth(0, 75)
        self.table.setColumnWidth(1, 110)
        self.table.cellChanged.connect(self.schedule_save)
        self.table.cellClicked.connect(self._segment_clicked)
        self.transcript_stack = QStackedWidget()
        self.transcript_stack.addWidget(self.table)
        empty = QWidget()
        empty_layout = QVBoxLayout(empty)
        empty_layout.setContentsMargins(22, 18, 22, 18)
        empty_layout.addStretch(1)
        self.empty_title = self._label('Every meeting, clearly captured.', 'Headline')
        self.empty_title.setWordWrap(True)
        empty_layout.addWidget(self.empty_title)
        self.empty_hint = self._label('Record a conversation, add an audio or video file, or paste notes to get started.', 'Muted')
        self.empty_hint.setWordWrap(True)
        empty_layout.addWidget(self.empty_hint)
        empty_layout.addSpacing(8)
        empty_layout.addWidget(self._label('Capture the words  →  Review your transcript  →  Create your notes', 'Hint'))
        empty_layout.addStretch(1)
        self.transcript_stack.addWidget(empty)
        t_layout.addWidget(self.transcript_stack, 1)
        self.tabs.addTab(transcript_tab, 'Transcript')
        self.doc_edits = {}
        for name in ('Summary', 'Minutes', 'Memo', 'Action items'):
            page = QWidget()
            layout = QVBoxLayout(page)
            layout.setContentsMargins(10, 10, 10, 10)
            layout.setSpacing(9)
            layout.addWidget(self._label('Make this your own · edit anything, then save a copy when ready.', 'Hint'))
            text = QTextEdit()
            text.setAcceptRichText(False)
            text.setPlaceholderText('Click Create notes, or start writing here…')
            text.setLineWrapMode(QTextEdit.WidgetWidth)
            text.textChanged.connect(self.schedule_save)
            layout.addWidget(text, 1)
            self.doc_edits[name] = text
            self.tabs.addTab(page, name)
        details_page = QWidget()
        details_layout = QVBoxLayout(details_page)
        details_layout.addWidget(self._label('Meeting details · saved automatically', 'Hint'))
        details_scroll = QScrollArea()
        details_scroll.setWidgetResizable(True)
        details_scroll.setWidget(details_box)
        details_layout.addWidget(details_scroll)
        self.tabs.addTab(details_page, 'Meeting details')
        settings_page = QWidget()
        settings_layout = QVBoxLayout(settings_page)
        settings_hint = self._label('Choose how SolScribe turns speech into text. The defaults work well for most meetings.', 'Hint')
        settings_hint.setWordWrap(True)
        settings_layout.addWidget(settings_hint)
        settings_layout.addLayout(controls)
        settings_layout.addLayout(live_controls)
        settings_layout.addLayout(writing_controls)
        helper_hint = self._label('Quick notes work straight away. Polished notes use an optional writing helper on this PC. If it is unavailable, you still get quick notes.', 'Hint')
        helper_hint.setWordWrap(True)
        settings_layout.addWidget(helper_hint)
        advanced_toggle = QToolButton()
        advanced_toggle.setText('Advanced writing setup')
        advanced_toggle.setCheckable(True)
        advanced_toggle.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        advanced_toggle.setArrowType(Qt.RightArrow)
        settings_layout.addWidget(advanced_toggle)
        advanced = QWidget()
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.setContentsMargins(0, 4, 0, 0)
        advanced_hint = self._label('Polished notes use Ollama, a separate app that runs on your PC. Install it and add a writing model, then enter its name below.', 'Hint')
        advanced_hint.setWordWrap(True)
        advanced_layout.addWidget(advanced_hint)
        advanced_layout.addWidget(self.ollama_model)
        setup_link = self._label('<a href="https://github.com/zibah04/Solscribe/blob/codex/windows-build-v0.2/README.md#optional-better-local-ai-minutes">Open the writing helper setup guide</a>', 'Hint')
        setup_link.setOpenExternalLinks(True)
        advanced_layout.addWidget(setup_link)
        advanced.hide()
        advanced_toggle.toggled.connect(advanced.setVisible)
        advanced_toggle.toggled.connect(lambda checked: advanced_toggle.setArrowType(Qt.DownArrow if checked else Qt.RightArrow))
        settings_layout.addWidget(advanced)
        storage_row = QHBoxLayout()
        for label, callback in [('Back up meetings', self.backup_meetings), ('Restore backup', self.restore_meetings), ('Trash', self.show_trash)]:
            button = self._button(label, 'Plain')
            button.clicked.connect(callback)
            storage_row.addWidget(button)
        settings_layout.addLayout(storage_row)
        backup_hint = self._label('Backups include app-owned recordings and notes. Imported files stay in their original location; keep those separately.', 'Hint')
        backup_hint.setWordWrap(True)
        settings_layout.addWidget(backup_hint)
        self._engine_changed()
        settings_layout.addStretch(1)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_page)
        self.tabs.addTab(settings_scroll, 'Settings')
        work.addWidget(self.tabs, 1)

        bottom = QHBoxLayout()
        self.capture_mode = QComboBox()
        for label, mode in [('Microphone', 'microphone'), ('Computer audio', 'system'), ('Both sources', 'combined')]:
            self.capture_mode.addItem(label, mode)
        self.capture_mode.setAccessibleName('Recording source mode')
        self.capture_mode.setCurrentIndex(max(0, self.capture_mode.findData(str(self.settings.value('capture_mode', 'microphone')))))
        self.capture_mode.currentIndexChanged.connect(lambda _: self.settings.setValue('capture_mode', self.capture_mode.currentData()))
        bottom.addWidget(self.capture_mode)
        self.system_combo = QComboBox()
        self.system_combo.addItem('Default playback device', None)
        self.system_combo.setAccessibleName('Computer audio output device')
        source_row = QHBoxLayout()
        source_row.addWidget(self._label('Computer audio device', 'SettingLabel'))
        source_row.addWidget(self.system_combo, 1)
        settings_layout.insertLayout(2, source_row)
        bottom.addStretch(1)
        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(180)
        self.mic_combo.setMaximumWidth(330)
        self.mic_combo.setToolTip('Audio input to use for microphone recording.')
        bottom.addWidget(self.mic_combo)
        work.addLayout(bottom)
        self.statusBar()

        for control, name in [(self.title_edit, 'Meeting title'), (self.date_edit, 'Meeting date'),
                              (self.attendees_edit, 'Attendees'), (self.location_edit, 'Location'),
                              (self.chair_edit, 'Chairperson'), (self.agenda_edit, 'Agenda'),
                              (self.model_combo, 'Transcript quality'), (self.live_model_combo, 'Caption quality'),
                              (self.language_combo, 'Spoken language'), (self.engine_combo, 'Note style'),
                              (self.mic_combo, 'Recording input'), (self.search_library, 'Search meetings'),
                              (self.search_transcript, 'Search transcript'), (self.table, 'Editable transcript')]:
            control.setAccessibleName(name)
        for name, editor in self.doc_edits.items():
            editor.setAccessibleName(f'{name} editor')

        self.setAcceptDrops(True)

    def set_theme(self, name):
        self.theme_name = name if name in THEMES else 'dark'
        self.settings.setValue('theme', self.theme_name)
        self.theme_combo.blockSignals(True)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.theme_name))
        self.theme_combo.blockSignals(False)
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
        for shortcut, fn in [('Ctrl+,', lambda: self.tabs.setCurrentIndex(6)), ('Ctrl+N', self.new_session), ('Ctrl+O', self.import_audio),
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
                    self.mic_combo.addItem('PC audio: ' + name, 'loopback:' + device_id)
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
        self.title_edit.setText(session['title'])
        self.title_edit.setCursorPosition(0)
        self.title_edit.setToolTip(session['title'])
        self.date_edit.setText(session['meeting_date'])
        self.attendees_edit.setText(session['attendees'])
        self.location_edit.setText(session['location'])
        self.chair_edit.setText(session['chair'])
        self.agenda_edit.setText(session['agenda'])
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for idx, segment in enumerate(session['segments']):
            self.table.insertRow(idx)
            start = QTableWidgetItem(stamp(segment.get('start', 0)))
            start.setFlags(start.flags() & ~Qt.ItemIsEditable)
            start.setData(Qt.UserRole, float(segment.get('start') or 0))
            start.setData(Qt.UserRole + 1, float(segment.get('end') or 0))
            self.table.setItem(idx, 0, start)
            self.table.setItem(idx, 1, QTableWidgetItem(segment.get('speaker') or 'Speaker'))
            self.table.setItem(idx, 2, QTableWidgetItem(segment.get('text') or ''))
        self.table.blockSignals(False)
        self.search_transcript.clear()
        self.caption_status.setText('Your words are saved · record another meeting or create notes' if session['segments'] else 'Your transcript will appear below')
        for name, field in [('Summary', 'summary'), ('Minutes', 'minutes'), ('Memo', 'memo'), ('Action items', 'actions')]:
            self.doc_edits[name].setMarkdown(session.get(field) or '')
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
        self.update_actions()
        self.status_label.setText('Saved on this PC · changes save automatically')

    def update_actions(self):
        has_audio = bool(self.current_session and self.current_session.get('audio_path') and
                         Path(self.current_session['audio_path']).is_file())
        transcribing = bool(self._worker and self._worker.isRunning())
        live_working = bool(self._live_worker and self._live_worker.isRunning())
        reporting = bool(self._report_worker and self._report_worker.isRunning())
        recording = self.record_timer.isActive()
        storage_busy = bool(self._storage_worker and self._storage_worker.isRunning())
        stopping = bool(self._stop_worker and self._stop_worker.isRunning())
        busy = transcribing or reporting or live_working or storage_busy or stopping
        has_words = bool(self.current_session and self.current_session.get('segments'))
        self.transcript_stack.setCurrentIndex(0 if self.table.rowCount() else 1)
        if recording or live_working:
            self.empty_title.setText('Your words will appear here.')
            self.empty_hint.setText('Keep speaking naturally. First use may need a speech download; your recording is being saved.')
        elif has_audio:
            self.empty_title.setText('Your recording is ready.')
            self.empty_hint.setText('Choose Create transcript to turn the recording into words you can review and edit.')
        else:
            self.empty_title.setText('Every meeting, clearly captured.')
            self.empty_hint.setText('Record a conversation, add an audio or video file, or paste notes to get started.')
        for control in (self.capture_mode, self.system_combo, self.mic_combo, self.live_checkbox, self.live_model_combo, self.language_combo):
            control.setEnabled(not recording and not live_working)
        self.transcribe_btn.setEnabled((has_audio and not reporting and not recording and not live_working) or transcribing)
        if not transcribing:
            self.transcribe_btn.setText('Improve transcript' if has_words and has_audio else 'Create transcript')
        self.record_btn.setEnabled(not stopping and not storage_busy)
        self.speakers_btn.setEnabled(has_words and not busy and not recording)
        self.report_btn.setEnabled(has_words and not busy and not recording)
        self.export_btn.setEnabled(bool(has_words or any(edit.toPlainText().strip() for edit in self.doc_edits.values())) and not recording and not busy)
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
            hint = 'Record a meeting or add a recording to begin.'
        if self._save_error:
            hint = 'Changes are not saved yet. Check available disk space and try again.'
        self.flow_hint.setText(hint)
        self.delete_btn.setEnabled(not busy and not recording)
        for control in (self.title_edit, self.table, self.date_edit, self.attendees_edit, self.location_edit, self.chair_edit, self.agenda_edit):
            control.setEnabled(not storage_busy)
        for control in (self.new_btn, self.import_btn, self.paste_btn, self.demo_btn,
                        self.library, self.search_library):
            control.setEnabled(not busy and not recording)

    def _is_busy(self):
        return bool((self._stop_worker and self._stop_worker.isRunning()) or
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
        session_id = self.store.create('Untitled meeting')
        self.search_library.clear()
        self.reload_library(select_id=session_id)
        self.tabs.setCurrentIndex(0)
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
        session_id = self.store.demo()
        self.search_library.clear()
        self.reload_library(select_id=session_id)
        self.caption_status.setText('Example meeting · sample text. Click Record meeting to capture your own words.')
        self.statusBar().showMessage('Example meeting loaded. Try Create notes.', 8000)

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
        session_id = self.store.create(path.stem.replace('_', ' '), str(path.resolve()))
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
                            'Paste a transcript or meeting notes here:')
        if not ok or not content.strip():
            return
        if not self.persist():
            return
        session_id = self.store.create('Pasted meeting notes')
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
        if any(session.get(k) for k in ('summary', 'minutes', 'memo', 'actions')):
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
        self._report_worker = ReportWorker(session, method, model, self)
        self._report_worker.status.connect(self._work_status)
        self._report_worker.done.connect(self._reports_ready)
        self._report_worker.failed.connect(self._report_failed)
        self._report_worker.finished.connect(self.update_actions)
        self.progress.setRange(0, 0)
        self.progress.show()
        self._report_worker.start()
        self.update_actions()

    def _reports_ready(self, output):
        self.progress.hide()
        target_id = self._report_session_id
        self.store.update(target_id, summary=output['summary'], minutes=output['minutes'],
                          memo=output['memo'], actions=output['actions'])
        if self.session_id == target_id:
            self.load_session(target_id)
        self.tabs.setCurrentIndex(1)
        if output.get('fallback'):
            self._notes_notice = 'Quick notes are ready. The optional writing helper is unavailable.'
            self._notes_details = output.get('details', '')
        else:
            self._notes_notice = ''
            self._notes_details = ''
        self.status_label.setText('✓ Your notes are ready. Edit anything, then save a copy.')
        self.statusBar().showMessage('Summary, minutes, memo and action list saved.', 9000)
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
        new_title = self.title_edit.text().strip() or 'Untitled meeting'
        try:
            self.store.update(self.session_id, title=new_title, segments=segments,
                              meeting_date=self.date_edit.text().strip(),
                              attendees=self.attendees_edit.text().strip(),
                              location=self.location_edit.text().strip(),
                              chair=self.chair_edit.text().strip(),
                              agenda=self.agenda_edit.text().strip(),
                              summary=self.doc_edits['Summary'].toMarkdown().strip(),
                              minutes=self.doc_edits['Minutes'].toMarkdown().strip(),
                              memo=self.doc_edits['Memo'].toMarkdown().strip(),
                              actions=self.doc_edits['Action items'].toMarkdown().strip())
            self.current_session = self.store.get(self.session_id)
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
        action = more.addAction('All meeting data (.json)')
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
                                   'Audio transcription or report generation is still running. Close the app after it completes.')
            event.ignore()
            return
        if not self.persist():
            self._show_error('Your changes are not saved yet',
                             'Please check available disk space and try again. Keep this window open to protect your edits.',
                             self._save_error)
            event.ignore()
            return
        event.accept()

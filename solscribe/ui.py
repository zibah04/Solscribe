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
    QToolButton, QAbstractItemView, QInputDialog, QApplication, QSizePolicy, QScrollArea,
)

from .storage import Store
from .recorder import MicrophoneRecorder, SystemLoopbackRecorder
from .transcriber import TranscriptionWorker
from .live import LiveTranscriptionWorker
from .reports import draft_local, draft_ai, stamp
from .exporters import export_file, safe_filename

SUPPORTED_AUDIO = {'.wav', '.mp3', '.m4a', '.mp4', '.mpeg', '.mpga',
                   '.aac', '.ogg', '.flac', '.webm', '.wma', '.mov'}

STYLE = r'''
QWidget { background: #0B1120; color: #E7EAF4; font-family: "Segoe UI"; font-size: 10pt; }
QLabel, QCheckBox { background: transparent; }
QMainWindow, QWidget#AppRoot { background: #0B1120; }
QFrame#Sidebar { background: #111A2D; border-right: 1px solid #27314B; }
QLabel#LogoIcon { color: white; background: #7567E8; border-radius: 12px; font-size: 20pt; font-weight: bold; }
QLabel#Brand { color: #F8F9FC; font-size: 19pt; font-weight: 700; }
QLabel#BrandTag { color: #9EA7C0; font-size: 9pt; }
QLabel#Eyebrow { color: #9AABC8; font-size: 9pt; font-weight: 700; letter-spacing: 1px; }
QLabel#Hint, QLabel#Muted { color: #98A4BE; font-size: 9pt; }
QLabel#Headline { color: white; font-size: 17pt; font-weight: 700; }
QFrame#Panel { background: #141E32; border: 1px solid #27334D; border-radius: 15px; }
QFrame#SettingPanel { background: #111A2C; border: 1px solid #25304B; border-radius: 11px; }
QLabel#SettingLabel { color: #9EACC5; font-size: 9pt; }
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox { background: #0C1526; border: 1px solid #2B3856; border-radius: 8px; padding: 6px; color: #F0F2F8; selection-background-color: #7167DE; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #8A7DF8; }
QLineEdit#TitleInput { background: transparent; border: none; padding: 0px; font-size: 19pt; font-weight: 700; color: white; }
QLineEdit#TitleInput:focus { border: none; }
QComboBox { padding: 7px 10px; }
QComboBox QAbstractItemView { background: #1B2740; border: 1px solid #546084; color: white; selection-background-color: #4A468B; }
QPushButton { background: #25324A; border: 1px solid #354361; border-radius: 9px; padding: 8px 12px; color: #E8EBF6; font-weight: 600; }
QPushButton:hover { background: #33425E; }
QPushButton:pressed { background: #263551; }
QPushButton:disabled { background: #1B2436; color: #63718B; border-color: #253048; }
QPushButton#Primary { background: #7467E8; border-color: #7467E8; color: white; }
QPushButton#Primary:hover { background: #8C81F5; }
QPushButton#Primary:disabled { background: #1B2436; color: #63718B; border-color: #253048; }
QCheckBox { color: #C7C2FF; font-size: 9pt; spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; }
QPushButton#Record { background: #3B2539; border-color: #75415A; color: #FFB5CC; }
QPushButton#Record:hover { background: #60314A; }
QPushButton#Recording { background: #B63D60; color: white; border-color: #E46C91; }
QPushButton#Plain { background: transparent; border: 1px solid #33425E; color: #CFD6E8; }
QPushButton#Plain:hover { background: #24324D; }
QPushButton#Small { padding: 8px 12px; }
QListWidget { background: transparent; border: none; outline: none; padding: 3px; }
QListWidget::item { background: transparent; color: #C5CDE0; border-radius: 9px; padding: 11px 10px; margin: 2px 0; }
QListWidget::item:hover { background: #202D46; }
QListWidget::item:selected { background: #2A305D; color: #FFFFFF; border: 1px solid #554F9B; }
QTabWidget::pane { border: 1px solid #2A3550; border-radius: 10px; background: #121B2D; top: -1px; }
QTabBar::tab { background: transparent; color: #A3ADC5; padding: 9px 12px; font-weight: 600; border-bottom: 2px solid transparent; }
QTabBar::tab:hover { color: white; }
QTabBar::tab:selected { color: #C4BDFF; border-bottom: 2px solid #8D80FA; }
QTableWidget { background: #111B2C; alternate-background-color: #172238; border: none; gridline-color: #293652; selection-background-color: #323B67; selection-color: white; }
QTableWidget::item { padding: 8px; }
QHeaderView::section { background: #1D2A42; color: #AEBBD2; padding: 11px; border: none; border-bottom: 1px solid #36435E; font-weight: 650; }
QScrollBar:vertical { background: #121B2B; width: 11px; margin: 1px; }
QScrollBar::handle:vertical { background: #34435F; border-radius: 5px; min-height: 28px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar:horizontal { background: #121B2B; height: 10px; }
QScrollBar::handle:horizontal { background: #34435F; border-radius: 5px; }
QProgressBar { background: #27334D; border: none; border-radius: 4px; height: 7px; text-align: center; }
QProgressBar::chunk { background: #8B7BFA; border-radius: 4px; }
QSlider::groove:horizontal { height: 5px; background: #34435F; border-radius: 2px; }
QSlider::handle:horizontal { background: #A69AFF; width: 12px; margin: -4px 0; border-radius: 6px; }
QMenu { background: #18253B; border: 1px solid #3E4A64; padding: 6px; color: white; }
QMenu::item { padding: 8px 23px; border-radius: 5px; }
QMenu::item:selected { background: #504B92; }
QStatusBar { color: #9CA9C1; background: #0B1120; border-top: 1px solid #25314B; }
QMessageBox, QInputDialog, QFileDialog { background: #111B2E; }
'''


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


class MainWindow(QMainWindow):
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
        self.recorder = MicrophoneRecorder()
        self.setWindowTitle('SolScribe 0.2.2 · Meeting notes')
        self.setMinimumSize(1000, 640)
        self.resize(1400, 830)
        self.setStyleSheet(STYLE)
        self._build_ui()
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
        self.reload_library()
        if not self.session_id:
            self.new_session()
        self.statusBar().showMessage('Your recordings and transcripts are stored locally.', 7500)

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
        self.new_btn = self._button('＋  New session', 'Primary')
        self.new_btn.clicked.connect(self.new_session)
        sidebar.addWidget(self.new_btn)
        self.import_btn = self._button('↥  Add a recording', 'Plain')
        self.import_btn.clicked.connect(self.import_audio)
        sidebar.addWidget(self.import_btn)
        self.record_btn = self._button('●  Record meeting', 'Record')
        self.record_btn.clicked.connect(self.toggle_record)
        sidebar.addWidget(self.record_btn)
        self.paste_btn = self._button('≡  Paste text', 'Plain')
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
        self.demo_btn = self._button('✦  Example meeting', 'Plain')
        self.demo_btn.setToolTip('Opens a saved sample transcript, not a live microphone demo.')
        self.demo_btn.clicked.connect(self.load_demo)
        sidebar.addWidget(self.demo_btn)
        self.folder_btn = self._button('▣  Open local data folder', 'Plain')
        self.folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.store.root))))
        sidebar.addWidget(self.folder_btn)
        sidebar.addWidget(self._label('PRIVATE · STORED ON THIS PC', 'Hint'))

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
        self.delete_btn = self._button('Delete', 'Plain')
        self.delete_btn.clicked.connect(self.delete_session)
        header.addWidget(self.delete_btn)
        self.export_btn = self._button('↓  Save a copy', 'Plain')
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
        self.play_btn = self._button('▶  Play', 'Small')
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
        self.transcribe_btn = self._button('✦  Create transcript', 'Primary')
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
        self.report_btn = self._button('✧  Create notes', 'Primary')
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
        t_layout.addWidget(self.table, 1)
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
        self._engine_changed()
        settings_layout.addStretch(1)
        settings_scroll = QScrollArea()
        settings_scroll.setWidgetResizable(True)
        settings_scroll.setWidget(settings_page)
        self.tabs.addTab(settings_scroll, 'Settings')
        work.addWidget(self.tabs, 1)

        bottom = QHBoxLayout()
        bottom.addWidget(self._label('Microphone / PC audio', 'Hint'))
        bottom.addStretch(1)
        self.mic_combo = QComboBox()
        self.mic_combo.setMinimumWidth(180)
        self.mic_combo.setMaximumWidth(330)
        self.mic_combo.setToolTip('Audio input to use for microphone recording.')
        bottom.addWidget(self.mic_combo)
        work.addLayout(bottom)
        self.statusBar()

        self.setAcceptDrops(True)

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
        for shortcut, fn in [('Ctrl+N', self.new_session), ('Ctrl+O', self.import_audio),
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
            if self.session_id:
                self.persist()
            self.load_session(current.data(Qt.UserRole))

    def load_session(self, session_id):
        session = self.store.get(session_id)
        if not session:
            return
        self._loading = True
        self.session_id = session_id
        self.current_session = session
        self.title_edit.setText(session['title'])
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
        self.caption_status.setText('Your words are saved · record another meeting or create notes')
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
            self.audio_name.setText('Recording not found' if path else 'Written notes · no recording attached')
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
        busy = transcribing or reporting or live_working
        has_words = bool(self.current_session and self.current_session.get('segments'))
        for control in (self.mic_combo, self.live_checkbox, self.live_model_combo, self.language_combo):
            control.setEnabled(not recording and not live_working)
        self.transcribe_btn.setEnabled((has_audio and not reporting and not recording and not live_working) or transcribing)
        if not transcribing:
            self.transcribe_btn.setText('✦  Improve transcript' if has_words and has_audio else '✦  Create transcript')
        self.report_btn.setEnabled(has_words and not busy and not recording)
        for edit in self.doc_edits.values():
            edit.setReadOnly(reporting)
        has_notice = self.session_id == self._notes_session_id and bool(self._notes_notice)
        self.notes_details_btn.setVisible(has_notice and not busy and not recording)
        if recording:
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
        self.flow_hint.setText(hint)
        self.delete_btn.setEnabled(not busy and not recording)
        for control in (self.new_btn, self.import_btn, self.paste_btn, self.demo_btn,
                        self.library, self.search_library):
            control.setEnabled(not busy and not recording)

    def _is_busy(self):
        return bool((self._worker and self._worker.isRunning()) or
                    (self._report_worker and self._report_worker.isRunning()) or
                    (self._live_worker and self._live_worker.isRunning()))

    def new_session(self):
        if self._is_busy():
            return
        if self.record_timer.isActive():
            QMessageBox.warning(self, 'Recording in progress', 'Stop the recording before creating another session.')
            return
        self.persist()
        session_id = self.store.create('Untitled meeting')
        self.search_library.clear()
        self.reload_library(select_id=session_id)
        self.tabs.setCurrentIndex(0)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def load_demo(self):
        if self._is_busy():
            return
        if self.record_timer.isActive():
            return
        self.persist()
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
        self.persist()
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
        self.persist()
        session_id = self.store.create('Pasted meeting notes')
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        segments = [{'start': 0, 'end': 0, 'speaker': 'Written notes', 'text': line} for line in lines]
        self.store.update(session_id, segments=segments, model='pasted text')
        self.search_library.clear()
        self.reload_library(select_id=session_id)

    def _live_option_changed(self, enabled):
        self.settings.setValue('live_captions', enabled)
        if not self.record_timer.isActive():
            self.record_btn.setText('●  Record meeting')

    def toggle_record(self):
        if self.record_timer.isActive():
            try:
                self.persist()
                path = self.recorder.stop()
                self.record_timer.stop()
                self.record_btn.setText('●  Record meeting')
                self.record_btn.setObjectName('Record')
                self.record_btn.style().unpolish(self.record_btn)
                self.record_btn.style().polish(self.record_btn)
                if self.session_id:
                    self.store.update(self.session_id, audio_path=str(path),
                                      duration=self.recorder.elapsed)
                    self.load_session(self.session_id)
                if self._live_worker and self._live_worker.isRunning():
                    self._live_worker.stop()
                    self.status_label.setText('Recording saved · finishing the last words…')
                    self.caption_status.setText('Recording saved · finishing the last words…')
                else:
                    self.status_label.setText(f'Recording saved · {stamp(self.recorder.elapsed)} · Ready to transcribe')
                if self.recorder.live_dropped:
                    QMessageBox.warning(self, 'Some words could not keep up',
                        'Your full recording is safe. Choose Improve transcript to fill in any words that were missed while recording.')
                if self.recorder.error or self.recorder.elapsed < 0.2:
                    self._show_error('Check your recording',
                                     'Some sound may be missing. Play the recording to check it, and make sure the right microphone is selected.',
                                     self.recorder.error or 'There is almost no sound in this recording.')
            except Exception as exc:
                self._show_error('Could not finish recording',
                                 'Please check your saved recording before starting another meeting.', exc)
            finally:
                self.update_actions()
            return
        if self._is_busy():
            QMessageBox.information(self, 'Busy', 'Complete the current task before recording.')
            return
        if not self.session_id:
            self.new_session()
        # A new audio capture must never silently mismatch an old transcript.
        if self.current_session and (self.current_session.get('audio_path') or self.current_session.get('segments')):
            self.new_session()
            self.title_edit.setText('Meeting · ' + datetime.now().strftime('%d %b %Y %H:%M'))
            self.persist()
        self.persist()
        path = self.store.recordings / f'{uuid.uuid4().hex}.wav'
        live_enabled = self.live_checkbox.isChecked()
        self._live_failed_message = None
        try:
            selected_device = self.mic_combo.currentData()
            if isinstance(selected_device, str) and selected_device.startswith('loopback:'):
                self.recorder = SystemLoopbackRecorder()
                device = selected_device[len('loopback:'):]
            else:
                self.recorder = MicrophoneRecorder()
                device = selected_device
            live_queue = queue.Queue(maxsize=3500) if live_enabled else None
            self.recorder.live_queue = live_queue
            self.recorder.start(path, device)
            self.store.update(self.session_id, audio_path=str(path), duration=0,
                              model='live' if live_enabled else '')
            self.current_session = self.store.get(self.session_id)
            self.audio_name.setText('Recording this meeting…')
            self.playback_controls.hide()
            if live_enabled:
                model = self.live_model_combo.currentData()
                self._live_session_id = self.session_id
                self._live_failed_message = None
                self.caption_status.setText('Getting ready to listen · first use needs a download. Your recording is safe.')
                self.search_transcript.clear()
                self._live_worker = LiveTranscriptionWorker(
                    live_queue, model, self.language_combo.currentData(), self.store.models, self)
                self._live_worker.status.connect(self._live_status)
                self._live_worker.segment_batch.connect(self._live_segments)
                self._live_worker.failed.connect(self._live_failed)
                self._live_worker.finished.connect(self._live_finished)
                self._live_worker.start()
                self.tabs.setCurrentIndex(0)
            else:
                self.caption_status.setText('Recording only · enable live transcription before your next recording for captions')
            self.record_btn.setText('■  Stop recording')
            self.record_btn.setObjectName('Recording')
            self.record_btn.style().unpolish(self.record_btn)
            self.record_btn.style().polish(self.record_btn)
            self.status_label.setText('Recording · getting ready to show your words…' if live_enabled
                                      else 'Recording…')
            self.record_timer.start()
            self.update_actions()
        except Exception as exc:
            if self.recorder.active:
                self.recorder.stop()
            self._show_error('Microphone unavailable',
                'We could not start recording. Choose another microphone below, or allow microphone access in Windows Settings.', exc)

    def _refresh_recording(self):
        duration = stamp(self.recorder.elapsed)
        bars = int(min(1, self.recorder.level * 7) * 12)
        caption = ' · LIVE' if self._live_worker and self._live_worker.isRunning() else ''
        if self._live_worker and self._live_worker.isRunning():
            behind = max(0, int(self.recorder.elapsed - self._live_worker.processed_seconds))
            caption += f' · ~{behind}s pending' if behind >= 10 else ''
        if self._live_failed_message:
            caption = ' · WORDS UNAVAILABLE · recording continues'
        elif self.recorder.elapsed >= 3 and self.recorder.level < 0.0001:
            caption += ' · No sound detected · check your microphone'
        self.status_label.setText(f'● Recording {duration}{caption}    {"▮" * bars}{"▯" * (12 - bars)}')
        if not self.recorder.active:
            # An audio backend may fail asynchronously (e.g., unplugged loopback).
            self.toggle_record()

    def _live_status(self, message):
        self.caption_status.setText(message)
        if not self.record_timer.isActive():
            self.status_label.setText(message)
        self.statusBar().showMessage(message, 6000)

    def _live_segments(self, new_segments):
        if self._live_session_id != self.session_id or not new_segments:
            return
        # No reload while recording, so the user's current focus and edits survive.
        self.table.blockSignals(True)
        for part in new_segments:
            row = self.table.rowCount()
            self.table.insertRow(row)
            time_cell = QTableWidgetItem(stamp(part.get('start', 0)))
            time_cell.setFlags(time_cell.flags() & ~Qt.ItemIsEditable)
            time_cell.setData(Qt.UserRole, float(part.get('start', 0)))
            time_cell.setData(Qt.UserRole + 1, float(part.get('end', 0)))
            self.table.setItem(row, 0, time_cell)
            self.table.setItem(row, 1, QTableWidgetItem(part.get('speaker') or 'Speaker'))
            self.table.setItem(row, 2, QTableWidgetItem(part.get('text') or ''))
        self.table.blockSignals(False)
        for row in range(self.table.rowCount() - len(new_segments), self.table.rowCount()):
            self.table.setRowHidden(row, False)
        self.table.scrollToBottom()
        self.persist()

    def _live_failed(self, message):
        self._live_failed_message = message
        self.caption_status.setText('Words cannot be shown right now. Your recording is safe; create a transcript when you finish.')
        self.status_label.setText('Recording continues · words are temporarily unavailable')

    def _live_finished(self):
        if not self.record_timer.isActive():
            self.persist()
            count = self.table.rowCount()
            message = ('Your recording is safe. Click Create transcript to recover the words.' if self._live_failed_message
                       else '✓ Your words are saved. Choose Improve transcript for a more accurate version.' if count
                       else 'No words recognized. Check your microphone and language, or try Create transcript.')
            self.status_label.setText(message)
            self.caption_status.setText(message)
        self.update_actions()

    def transcribe(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self.transcribe_btn.setText('Cancelling…')
            self.transcribe_btn.setEnabled(False)
            self.status_label.setText('Cancellation requested; waiting for the current segment…')
            return
        if not self.current_session or not self.current_session.get('audio_path'):
            return
        if self.current_session.get('segments'):
            reply = QMessageBox.question(self, 'Replace transcript?',
                    'Transcribing again will replace the current transcript and speaker labels. Continue?',
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        self.persist()
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

    def _transcribed(self, result):
        self.progress.hide()
        target_id = self._transcription_session_id
        self.store.update(target_id, **result)
        if self.session_id == target_id:
            self.load_session(target_id)
        self.reload_library(select_id=target_id)
        self.tabs.setCurrentIndex(0)
        self.status_label.setText(f'✓ Your transcript is ready. Edit anything or create notes.')
        self.statusBar().showMessage('Your words are saved on this PC. Create notes when you are ready.', 10000)

    def _transcription_finished(self):
        self.progress.hide()
        self.transcribe_btn.setText('✦  Create transcript')
        self.update_actions()

    def generate_reports(self):
        if self._is_busy() or self.record_timer.isActive():
            return
        self.persist()
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
            return
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
        active = self.library.currentItem()
        if active and active.data(Qt.UserRole) == self.session_id:
            active.setText(new_title + ('  ·  transcript' if segments else ''))

    def delete_session(self):
        if self._is_busy() or self.record_timer.isActive():
            return
        if not self.session_id:
            return
        response = QMessageBox.question(self, 'Delete meeting',
            'Delete this session, transcript, minutes and memo?\n\nImported source files will not be deleted.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if response != QMessageBox.Yes:
            return
        self.save_timer.stop()
        self.player.stop()
        self.store.delete(self.session_id)
        self.session_id = None
        self.current_session = None
        self.reload_library()
        if not self.session_id:
            self.new_session()

    def current_section(self):
        return {0: 'Transcript', 1: 'Summary', 2: 'Minutes', 3: 'Memo', 4: 'Action items'}.get(self.tabs.currentIndex(), 'Transcript')

    def show_export_menu(self):
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
        self.persist()
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
        self.play_btn.setText('Ⅱ  Pause' if state == QMediaPlayer.PlayingState else '▶  Play')

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
        self.persist()
        event.accept()

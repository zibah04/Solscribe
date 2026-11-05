"""Lecture mode, editable study notes and source-backed revision practice."""
import copy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTextEdit, QListWidget, QLineEdit, QPushButton, QLabel)
from ..lecture import source_hash
from ..reports import stamp
from .. import __version__


class StudyTools:
    def build_study_page(self):
        self.study_items = []
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(10, 10, 10, 10)
        self.study_notice = self._label('Create study notes to organize the lecture and practise with revision cards.', 'Hint')
        self.study_notice.setWordWrap(True)
        layout.addWidget(self.study_notice)
        self.study_tabs = QTabWidget()
        layout.addWidget(self.study_tabs, 1)
        self.study_edit = QTextEdit()
        self.study_edit.setAcceptRichText(False)
        self.study_edit.setPlaceholderText('Your lecture outline, key concepts, definitions and examples will appear here. You can also write your own notes.')
        self.study_edit.setAccessibleName('Study notes editor')
        self.study_edit.textChanged.connect(self.schedule_save)
        self.study_tabs.addTab(self.study_edit, 'Notes')
        revision = QWidget()
        row = QHBoxLayout(revision)
        self.revision_list = QListWidget()
        self.revision_list.setAccessibleName('Revision questions')
        self.revision_list.setMaximumWidth(310)
        self.revision_list.setMinimumWidth(140)
        row.addWidget(self.revision_list, 1)
        body = QVBoxLayout()
        row.addLayout(body, 2)
        hint = self._label('Try answering first, then reveal the source answer. You can edit the question and answer.', 'Hint')
        hint.setWordWrap(True)
        body.addWidget(hint)
        self.revision_question = QTextEdit()
        self.revision_question.setAcceptRichText(False)
        self.revision_question.setMaximumHeight(105)
        self.revision_question.setAccessibleName('Revision question editor')
        body.addWidget(self.revision_question)
        buttons = QHBoxLayout()
        self.reveal_answer = QPushButton('Show answer')
        self.reveal_answer.setCheckable(True)
        self.reveal_answer.toggled.connect(self._reveal_answer)
        buttons.addWidget(self.reveal_answer)
        self.revision_source = QPushButton('Check source')
        self.revision_source.clicked.connect(self._revision_source)
        buttons.addWidget(self.revision_source)
        buttons.addStretch(1)
        body.addLayout(buttons)
        self.revision_answer = QTextEdit()
        self.revision_answer.setAcceptRichText(False)
        self.revision_answer.setAccessibleName('Revision answer editor')
        body.addWidget(self.revision_answer, 1)
        self.revision_answer.hide()
        self.revision_list.currentRowChanged.connect(self._revision_selected)
        self.revision_question.textChanged.connect(self._revision_edited)
        self.revision_answer.textChanged.connect(self._revision_edited)
        self.study_tabs.addTab(revision, 'Revision')
        sources = QWidget()
        layout_sources = QVBoxLayout(sources)
        self.study_sources = QListWidget()
        self.study_sources.setAccessibleName('Study source passages')
        layout_sources.addWidget(self.study_sources, 1)
        self.study_quote = QTextEdit()
        self.study_quote.setReadOnly(True)
        self.study_quote.setAccessibleName('Original lecture excerpt')
        layout_sources.addWidget(self.study_quote, 1)
        self.study_jump = QPushButton('Go to transcript')
        self.study_jump.clicked.connect(self._study_jump)
        layout_sources.addWidget(self.study_jump)
        self.study_sources.currentRowChanged.connect(self._source_selected)
        self.study_tabs.addTab(sources, 'Sources')
        return page

    def session_type(self):
        return self.mode_combo.currentData() or 'meeting'

    def record_label(self):
        return 'Record lecture' if self.session_type() == 'lecture' else 'Record meeting'

    def _mode_changed(self):
        if self._loading or not self.session_id:
            return
        old = self.current_session.get('session_type', 'meeting')
        selected = self.session_type()
        # Save edits in both workspaces before applying the mode; a failed
        # commit restores the selector and keeps the visible edits in place.
        if not self.persist():
            self.mode_combo.blockSignals(True)
            self.mode_combo.setCurrentIndex(self.mode_combo.findData(old))
            self.mode_combo.blockSignals(False)
            return
        self.settings.setValue('new_session_type', selected)
        self.apply_session_type()
        self.focus_tab(0)

    def apply_session_type(self):
        lecture = self.session_type() == 'lecture'
        for index in range(1, 6):
            self.tabs.setTabVisible(index, not lecture)
        self.tabs.setTabVisible(7, lecture)
        self.report_btn.setText('Create study notes' if lecture else 'Create notes')
        self.new_btn.setText('New lecture' if lecture else 'New meeting')
        self.demo_btn.setText('Example lecture' if lecture else 'Example meeting')
        self.title_edit.setPlaceholderText('Name this lecture…' if lecture else 'Name this meeting…')
        self.title_edit.setAccessibleName('Lecture title' if lecture else 'Meeting title')
        if not self.record_timer.isActive():
            self.record_btn.setText(self.record_label())
        self.setWindowTitle(f'SolScribe {__version__} · ' + ('Lecture notes' if lecture else 'Meeting notes'))
        self.update_actions()

    def load_study(self, session):
        self.study_items = copy.deepcopy(session.get('study_items') or [])
        self.study_edit.setMarkdown(session.get('study_notes') or '')
        self.revision_list.clear()
        self.study_sources.clear()
        self._revision_indices = []
        for index, item in enumerate(self.study_items):
            self.study_sources.addItem(f'[{stamp(item["source_start"])}] {item["kind"].title()} · {item["title"]}')
            if item['kind'] == 'revision':
                self._revision_indices.append(index)
                self.revision_list.addItem(item['question'])
        self.revision_list.setCurrentRow(0 if self._revision_indices else -1)
        self._revision_selected(self.revision_list.currentRow())
        self.study_sources.setCurrentRow(0 if self.study_items else -1)
        self._source_selected(self.study_sources.currentRow())
        self.refresh_study_notice(session)

    def refresh_study_notice(self, session):
        fingerprint = session.get('study_source_hash')
        stale = bool(fingerprint and fingerprint != source_hash(session.get('segments') or []))
        message = ('The transcript has changed. These notes and source excerpts refer to the earlier words. Recreate notes when ready.' if stale
                   else 'Draft study aid · check terms and formulas. Notes and revision cards are edited separately; Sources keeps the original words.' if self.study_items
                   else 'Choose Create study notes for key concepts, definitions, examples and revision questions.')
        warnings = session.get('study_warnings') or []
        self.study_notice.setText(message + ('\n' + ' '.join(warnings) if warnings else ''))

    def _revision_selected(self, row):
        indices = getattr(self, '_revision_indices', [])
        item = self.study_items[indices[row]] if 0 <= row < len(indices) else None
        self._loading_card = True
        self.revision_question.setPlainText(item['question'] if item else '')
        self.revision_answer.setPlainText(item['answer'] if item else '')
        self.reveal_answer.setChecked(False)
        self.revision_answer.hide()
        for control in (self.reveal_answer, self.revision_source, self.revision_question):
            control.setEnabled(bool(item))
        self._loading_card = False

    def _revision_edited(self):
        if self._loading or getattr(self, '_loading_card', False):
            return
        row = self.revision_list.currentRow()
        if row < 0:
            return
        item = self.study_items[self._revision_indices[row]]
        item['question'] = self.revision_question.toPlainText()
        item['answer'] = self.revision_answer.toPlainText()
        item['verification'] = 'Edited by you · check source'
        self.revision_list.item(row).setText(item['question'])
        self.schedule_save()

    def _reveal_answer(self, checked):
        self.revision_answer.setVisible(checked)
        self.reveal_answer.setText('Hide answer' if checked else 'Show answer')

    def _revision_source(self):
        row = self.revision_list.currentRow()
        if row >= 0:
            self.study_sources.setCurrentRow(self._revision_indices[row])
            self.study_tabs.setCurrentIndex(2)

    def _source_selected(self, row):
        item = self.study_items[row] if 0 <= row < len(self.study_items) else None
        self.study_quote.setPlainText((f'[{stamp(item["source_start"])}] {item.get("verification", "Draft · check source")}\n\n' + item['evidence']) if item else 'No study sources yet. Create study notes first.')
        self.study_jump.setEnabled(bool(item))

    def _study_jump(self):
        row = self.study_sources.currentRow()
        if row < 0 or not self.table.rowCount():
            return
        if not self.persist():
            return
        item = self.study_items[row]
        start = item['source_start']
        nearest = min(range(self.table.rowCount()), key=lambda i: abs(float(self.table.item(i, 0).data(Qt.UserRole) or 0) - start))
        self.search_transcript.clear()
        self.table.setCurrentCell(nearest, 2)
        self.table.scrollToItem(self.table.item(nearest, 2))
        self.focus_tab(0)
        self.player.setPosition(int(start * 1000))
        self.statusBar().showMessage('Source position selected. If the transcript was edited, compare with the saved excerpt.', 10000)

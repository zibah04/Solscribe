"""Editable action register, draft review state and transcript evidence navigation."""
import copy
import uuid
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPlainTextEdit, QPushButton, QTableWidgetItem
from ..reports import stamp
from ..repository import timestamp


class ActionRegister:
    def load_actions(self, items):
        self._action_records = copy.deepcopy(items)
        self.action_table.blockSignals(True)
        self.action_table.setRowCount(len(items))
        for row, item in enumerate(items):
            for column, field in enumerate(('task', 'owner', 'deadline', 'status')):
                cell = QTableWidgetItem(str(item.get(field) or 'Unspecified'))
                cell.setToolTip('Review: ' + str(item.get('verification', 'Needs review')))
                self.action_table.setItem(row, column, cell)
            source = item.get('source_start')
            cell = QTableWidgetItem(stamp(source) if source is not None else 'Not linked')
            cell.setFlags(cell.flags() & ~Qt.ItemIsEditable)
            cell.setToolTip(item.get('evidence') or 'Manually entered task')
            self.action_table.setItem(row, 4, cell)
        self.action_table.blockSignals(False)

    def action_values(self):
        values = []
        for row in range(self.action_table.rowCount()):
            item = dict(self._action_records[row])
            for column, field in enumerate(('task', 'owner', 'deadline', 'status')):
                cell = self.action_table.item(row, column)
                item[field] = (cell.text().strip() if cell else '') or 'Unspecified'
            if any(item.get(field) != self._action_records[row].get(field) for field in ('task', 'owner', 'deadline', 'status')):
                item['verification'] = 'Edited by user'
            values.append(item)
        return values

    def add_action(self):
        if self._is_busy() or self.record_timer.isActive():
            return
        items = self.action_values()
        items.append({'id': uuid.uuid4().hex, 'task': 'New task', 'owner': 'Unspecified',
                      'deadline': 'Unspecified', 'status': 'Open', 'source_start': None,
                      'source_end': None, 'evidence': '', 'verification': 'Manually entered'})
        self.load_actions(items)
        self.action_table.setCurrentCell(len(items) - 1, 0)
        self.action_table.editItem(self.action_table.item(len(items) - 1, 0))
        self.edits_changed()

    def action_evidence(self, row, column):
        if column != 4 or row >= len(self._action_records):
            return
        item = self.action_values()[row]
        dialog = QDialog(self)
        dialog.setWindowTitle('Check the source words')
        dialog.resize(560, 300)
        layout = QVBoxLayout(dialog)
        label = QLabel('Review: ' + item.get('verification', 'Needs review'))
        layout.addWidget(label)
        text = QPlainTextEdit(item.get('evidence') or 'This task was entered manually and is not linked to recorded words.')
        text.setReadOnly(True)
        layout.addWidget(text)
        if item.get('source_start') is not None:
            button = QPushButton('Show in transcript')
            def navigate():
                self.focus_tab(0)
                start = item['source_start']
                for index in range(self.table.rowCount()):
                    cell = self.table.item(index, 0)
                    if cell and abs(float(cell.data(Qt.UserRole) or 0) - start) < .01:
                        self.table.selectRow(index)
                        self.table.scrollToItem(cell)
                        break
                if self.current_session and self.current_session.get('audio_path'):
                    self.player.setPosition(int(start * 1000))
                dialog.accept()
            button.clicked.connect(navigate)
            layout.addWidget(button)
        dialog.exec()

    def review_changed(self, checked):
        for checkbox in self.review_checks:
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)
        self.schedule_save()

    def show_notes_checks(self):
        dialog = QDialog(self)
        dialog.setWindowTitle('Notes review checks')
        dialog.resize(640, 400)
        layout = QVBoxLayout(dialog)
        label = QLabel('These checks help you review a draft; they cannot prove that every paraphrase is correct. Use action source times to inspect the original words.')
        label.setWordWrap(True)
        layout.addWidget(label)
        warnings = self.current_session.get('notes_warnings', []) if self.current_session else []
        text = QPlainTextEdit('\n\n'.join(warnings) or 'Review names, decisions, deadlines and assignments against your transcript before sharing.')
        text.setReadOnly(True)
        layout.addWidget(text)
        dialog.exec()

    def edits_changed(self, *args):
        if not self._loading:
            for checkbox in self.review_checks:
                checkbox.blockSignals(True)
                checkbox.setChecked(False)
                checkbox.blockSignals(False)
        self.schedule_save()

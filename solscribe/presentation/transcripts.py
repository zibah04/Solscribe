"""Compare improved words before replacement and provide bulk speaker editing."""
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPlainTextEdit, QDialogButtonBox, QInputDialog
from ..reports import transcript_text
from ..transcripts import preserve_speakers
from ..repository import timestamp


class TranscriptReview(QDialog):
    def __init__(self, previous, candidate, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Review improved transcript')
        available = self.screen().availableGeometry()
        self.resize(min(960, available.width() - 30), min(600, available.height() - 40))
        layout = QVBoxLayout(self)
        hint = QLabel('Compare the words before replacing your edits. Existing speaker names are carried across where the timing is clear. Your generated notes will be kept.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        columns = QHBoxLayout()
        for title, segments in [('Current transcript', previous), ('Improved draft', candidate)]:
            column = QVBoxLayout()
            column.addWidget(QLabel(title))
            text = QPlainTextEdit(transcript_text(segments))
            text.setReadOnly(True)
            column.addWidget(text)
            columns.addLayout(column)
        layout.addLayout(columns)
        buttons = QDialogButtonBox()
        keep = buttons.addButton('Keep current words', QDialogButtonBox.RejectRole)
        accept = buttons.addButton('Use improved draft', QDialogButtonBox.AcceptRole)
        keep.setDefault(True)
        keep.clicked.connect(self.reject)
        accept.clicked.connect(self.accept)
        layout.addWidget(buttons)


class TranscriptActions:
    def review_transcript(self, previous, candidate):
        return TranscriptReview(previous, candidate, self).exec() == QDialog.Accepted

    def rename_speakers(self):
        if self._is_busy() or self.record_timer.isActive() or not self.persist():
            return
        session = self.store.get(self.session_id)
        labels = sorted({part['speaker'] for part in session['segments']})
        if not labels:
            return
        old, okay = QInputDialog.getItem(self, 'Rename a speaker', 'Speaker label:', labels, 0, False)
        if not okay:
            return
        new, okay = QInputDialog.getText(self, 'Rename a speaker', 'Use this name throughout this transcript:', text=old)
        if not okay or not new.strip():
            return
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item and item.text() == old:
                item.setText(new.strip()[:200])
        self.table.blockSignals(False)
        self.edits_changed()
        self.persist()

    def _transcribed(self, result):
        self.progress.hide()
        target_id = self._transcription_session_id
        old = self.store.get(target_id)
        if not old:
            return
        values = dict(result)
        values['segments'] = preserve_speakers(old['segments'], result['segments'])
        if old['segments']:
            if not self.review_transcript(old['segments'], values['segments']):
                self.status_label.setText('Kept your current transcript and edits.')
                return
            history = old.get('transcript_history', [])[-2:]
            history.append({'saved_at': timestamp(), 'segments': old['segments'], 'model': old.get('model', '')})
            values['transcript_history'] = history
            values['reviewed_at'] = ''
        try:
            self.store.update(target_id, **values)
        except Exception as exc:
            self._save_error = str(exc)
            self._show_error('Could not save improved words', 'Your original transcript is kept. A recovery draft is retained when storage allows.', exc)
            return
        if self.session_id == target_id:
            self.load_session(target_id)
        self.reload_library(select_id=target_id)
        self.focus_tab(0)
        self.status_label.setText('Your transcript is ready. Existing notes were kept; review them against any changed words.')

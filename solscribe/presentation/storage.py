"""Backup, recovery and trash controls. File/archive work runs outside the UI thread."""
from pathlib import Path
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QFileDialog, QMessageBox, QInputDialog

from ..jobs import OperationWorker
from ..storage import Store


class StorageActions:
    def _storage_operation(self, operation, message, *, restoring=False):
        if self._is_busy() or self.record_timer.isActive() or not self.persist():
            return
        self._storage_restoring = restoring
        self._storage_succeeded = False
        self._storage_worker = OperationWorker(operation, self)
        self._storage_worker.done.connect(self._storage_done)
        self._storage_worker.failed.connect(lambda details: self._show_error('Storage operation did not finish',
            'Your current meeting data has been kept. Please check the destination and available space.', details))
        self._storage_worker.finished.connect(self._storage_finished)
        self.status_label.setText(message)
        self.progress.setRange(0, 0)
        self.progress.show()
        self._storage_worker.start()
        self.update_actions()

    def _storage_done(self, result):
        self._storage_succeeded = True
        if self._storage_restoring:
            self.store = Store(self.store.root)
            self.session_id, self.current_session = None, None
            self.reload_library()
            self.status_label.setText('Backup restored. Previous data is kept in the backups folder.')
        else:
            self.status_label.setText(f'Backup saved: {result}')

    def _storage_finished(self):
        self.progress.hide()
        if self._storage_restoring and self._storage_succeeded and not self.session_id:
            self.new_session()
        self.update_actions()

    def backup_meetings(self):
        if self._is_busy() or self.record_timer.isActive():
            return
        path, _ = QFileDialog.getSaveFileName(self, 'Back up meetings', str(Path.home() / 'SolScribe-backup.zip'), 'SolScribe backup (*.zip)')
        if path:
            store = self.store
            self._storage_operation(lambda: store.backup_archive(Path(path)), 'Backing up meetings and app recordings…')

    def restore_meetings(self):
        if self._is_busy() or self.record_timer.isActive():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Restore a backup', str(Path.home()), 'SolScribe backup (*.zip)')
        if not path:
            return
        if QMessageBox.question(self, 'Restore this backup?',
            'This replaces the current meeting library. A copy of your current database will be kept. Imported recordings remain linked to their original files.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        self.player.stop()
        store = self.store
        self._storage_operation(lambda: store.restore_archive(Path(path), confirm=True), 'Checking and restoring backup…', restoring=True)

    def delete_session(self):
        if self._is_busy() or self.record_timer.isActive() or not self.session_id or not self.persist():
            return
        if QMessageBox.question(self, 'Move meeting to trash?',
            'You can restore this meeting from Trash. Its recordings will be kept.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.player.stop()
            self.store.delete(self.session_id)
        except Exception as exc:
            self._show_error('Could not move this meeting', 'Your meeting has been kept. Please try again.', exc)
            return
        self.session_id, self.current_session = None, None
        self.reload_library()
        if not self.session_id:
            self.new_session()

    def show_trash(self):
        if self._is_busy() or self.record_timer.isActive() or not self.persist():
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('Meeting trash')
        dialog.resize(620, 420)
        layout = QVBoxLayout(dialog)
        hint = QLabel('Trashed meetings keep their recordings. Restore a meeting, or permanently remove its saved notes. Audio needs a separate confirmation.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        items = QListWidget()
        layout.addWidget(items)
        buttons = QHBoxLayout()
        restore = QPushButton('Restore meeting')
        purge = QPushButton('Permanently remove meeting…')
        audio = QPushButton('Unused recordings…')
        for button in (restore, purge, audio):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        def refresh():
            items.clear()
            for meeting in self.store.list(deleted=True):
                item = QListWidgetItem(meeting['title'])
                item.setData(Qt.UserRole, meeting['id'])
                items.addItem(item)
            restore.setEnabled(items.count() > 0)
            purge.setEnabled(items.count() > 0)
            if items.count():
                items.setCurrentRow(0)
        def act(permanent=False):
            selected = items.currentItem()
            if selected is None:
                return
            if permanent and QMessageBox.question(dialog, 'Permanently remove meeting?',
                'Its notes and transcript cannot be restored from Trash afterward. Recordings will still be kept until separately removed.',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
                return
            try:
                sid = selected.data(Qt.UserRole)
                self.store.purge(sid, confirm=True) if permanent else self.store.restore(sid)
                refresh()
                self.reload_library()
            except Exception as exc:
                self._show_error('Trash operation did not finish', 'Please try again. Recordings have been kept.', exc)
        restore.clicked.connect(lambda: act(False))
        purge.clicked.connect(lambda: act(True))
        audio.clicked.connect(self.remove_unused_recording)
        refresh()
        dialog.exec()

    def remove_unused_recording(self):
        with self.store.connect(write=False) as conn:
            rows = conn.execute("SELECT r.* FROM recordings r WHERE owned=1 AND state='ready' AND NOT EXISTS(SELECT 1 FROM session_recordings s WHERE s.recording_id=r.id)").fetchall()
        if not rows:
            QMessageBox.information(self, 'No unused app recordings', 'Referenced, imported and legacy recordings are protected.')
            return
        labels = [f'{Path(row["path"]).name} · {row["id"][:8]}' for row in rows]
        selected, okay = QInputDialog.getItem(self, 'Unused app recordings', 'Choose an app-owned recording that no meeting or trash item uses:', labels, 0, False)
        if not okay:
            return
        if QMessageBox.question(self, 'Permanently delete recording?', 'This audio cannot be recovered from the app afterward. Database-only backups do not contain audio.',
                                QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return
        try:
            self.store.purge_recording(rows[labels.index(selected)]['id'], confirm=True)
        except Exception as exc:
            self._show_error('Recording could not be removed', 'The file may still be in use or referenced. Please try again.', exc)

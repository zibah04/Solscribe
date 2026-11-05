"""Guide and update presentation, with saved work protected before installation."""
import os
import subprocess
import time
from pathlib import Path
from PySide6.QtCore import QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar, QCheckBox
from .. import __release_tag__
from ..jobs import OperationWorker
from ..update_transport import UpdateClient
from ..updates import verify_installer
from .welcome import QuickGuide


class UpdateDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle('SolScribe updates')
        self.setModal(False)
        layout = QVBoxLayout(self)
        heading = QLabel('Keep SolScribe up to date')
        heading.setObjectName('Headline')
        layout.addWidget(heading)
        layout.addWidget(QLabel('Current version: ' + __release_tag__.removeprefix('v').replace('-beta.', ' beta ')))
        self.message = QLabel('Check for a newer Windows version. You choose when to download and install it.')
        self.message.setWordWrap(True)
        layout.addWidget(self.message)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.preference = QCheckBox('Check for updates when SolScribe opens')
        self.preference.setChecked(window.auto_updates_checkbox.isChecked())
        self.preference.toggled.connect(window.auto_updates_checkbox.setChecked)
        layout.addWidget(self.preference)
        privacy = QLabel('Checks use GitHub over the internet. Recordings and meeting notes stay on this PC. '
                         'Windows may show an unknown publisher warning for this beta.')
        privacy.setWordWrap(True)
        privacy.setObjectName('Hint')
        layout.addWidget(privacy)
        buttons = QHBoxLayout()
        self.notes = QPushButton("Read what's new")
        self.notes.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(window._update_available.page_url)) if window._update_available else None)
        self.notes.hide()
        buttons.addWidget(self.notes)
        buttons.addStretch(1)
        self.later = QPushButton('Close')
        self.later.clicked.connect(self.reject)
        buttons.addWidget(self.later)
        self.primary = QPushButton('Check for updates')
        self.primary.setObjectName('Primary')
        self.primary.clicked.connect(window._update_primary)
        buttons.addWidget(self.primary)
        layout.addLayout(buttons)
        geometry = self.screen().availableGeometry()
        self.resize(min(600, geometry.width() - 30), min(330, geometry.height() - 40))

    def reject(self):
        if not self.parent()._update_install_active:
            super().reject()

    def closeEvent(self, event):
        if self.parent()._update_install_active:
            event.ignore()
        else:
            super().closeEvent(event)


class HelpUpdates:
    def init_help_updates(self):
        self._guide = self._update_dialog = None
        self._update_available = self._downloaded_update = None
        self._update_install_worker = None
        self._update_state = 'check'
        self._update_client = UpdateClient(self.store.root, __release_tag__, self)
        self._update_client.checked.connect(self._update_checked)
        self._update_client.failed.connect(self._update_failed)
        self._update_client.downloaded.connect(self._update_downloaded)
        self._update_client.progress.connect(self._update_progress)
        self._update_client.cancelled.connect(self._update_cancelled)
        self._update_auto_timer = QTimer(self)
        self._update_auto_timer.setSingleShot(True)
        self._update_auto_timer.timeout.connect(lambda: self.check_for_updates(manual=False))

    def start_first_run(self):
        if not self.settings.value('welcome_seen', False, type=bool):
            self.show_quick_guide()
        elif self.auto_updates_checkbox.isChecked():
            last = float(self.settings.value('updates_last_checked', 0) or 0)
            if time.time() - last >= 24 * 3600:
                self._update_auto_timer.start(1500)

    def show_quick_guide(self):
        if self._is_busy() or self.record_timer.isActive():
            self.statusBar().showMessage('Finish the current task before changing setup.', 6000)
            return
        if self._guide is not None:
            self._guide.raise_()
            return
        self.settings.setValue('welcome_seen', True)
        guide = QuickGuide(self)
        self._guide = guide
        guide.finished.connect(lambda result: self._guide_finished(guide, result))
        guide.open()

    def _guide_finished(self, guide, result):
        if result == QDialog.Accepted:
            self.capture_mode.setCurrentIndex(max(0, self.capture_mode.findData(guide.source.currentData())))
            self.mic_combo.setCurrentIndex(max(0, self.mic_combo.findData(guide.microphone.currentData())))
            self.live_checkbox.setChecked(guide.live_words.isChecked())
            self.auto_updates_checkbox.setChecked(guide.updates.isChecked())
            self.settings.setValue('welcome_completed', True)
            if guide.practice.isChecked():
                self.load_demo()
                self.focus_tab(0)
                self.statusBar().showMessage('Sample text is ready. Try Create notes, then Save a copy. Record meeting captures your own speech.', 15000)
        self._guide = None
        guide.deleteLater()

    def _auto_updates_changed(self, enabled):
        self.settings.setValue('check_updates_on_start', enabled)
        dialog = getattr(self, '_update_dialog', None)
        if dialog is not None:
            dialog.preference.blockSignals(True)
            dialog.preference.setChecked(enabled)
            dialog.preference.blockSignals(False)
        if enabled and hasattr(self, '_update_client'):
            self._update_auto_timer.start(0)

    def show_updates(self):
        if self._update_dialog is not None:
            self._update_dialog.raise_()
            return
        dialog = UpdateDialog(self)
        self._update_dialog = dialog
        dialog.finished.connect(lambda: self._update_dialog_closed(dialog))
        dialog.show()
        if self._downloaded_update is not None:
            self._show_update_state('ready')
        elif self._update_available is not None:
            self._show_update_state('available')
        elif self._update_client.active:
            self._show_update_state('checking')
        else:
            self.check_for_updates()

    def _update_dialog_closed(self, dialog):
        if self._update_client.active:
            self._update_client.cancel()
        self._update_dialog = None
        dialog.deleteLater()

    def check_for_updates(self, *, manual=True):
        if self._update_client.active or self._update_install_active:
            return
        if manual and self._update_dialog is None:
            self.show_updates()
            return
        self._show_update_state('checking')
        self._update_client.check(include_previews='-' in __release_tag__)

    def _update_checked(self, update):
        self.settings.setValue('updates_last_checked', time.time())
        if update != self._update_available:
            self._downloaded_update = None
        self._update_available = update
        if update is None:
            self._downloaded_update = None
            self.updates_btn.setText('Updates')
            self._show_update_state('check', "You're up to date.")
        else:
            self.updates_btn.setText('Update available')
            self._show_update_state('ready' if self._downloaded_update else 'available')
            self.statusBar().showMessage('A SolScribe update is available. Open Updates when you are ready.', 15000)

    def _show_update_state(self, state, message=None):
        self._update_state = state
        labels = {'check': ('Check for updates', 'Check for a newer Windows version.'),
                  'checking': ('Checking…', 'Checking for a newer version…'),
                  'available': ('Download update', 'A newer SolScribe version is ready: ' + (self._update_available.display_version if self._update_available else '')),
                  'downloading': ('Downloading…', 'Downloading your update. You can cancel and keep using this version.'),
                  'ready': ('Install and close' if self._supports_update_installation() else 'Open Windows download',
                            'Your update is ready. Your meetings will be saved and backed up before the installer opens.'),
                  'preparing': ('Preparing…', 'Saving your meetings and preparing the update…')}
        button, text = labels[state]
        self.update_status_label.setText(message or text)
        dialog = self._update_dialog
        if dialog is not None:
            dialog.message.setText(message or text)
            dialog.primary.setText(button)
            dialog.primary.setEnabled(state not in ('checking', 'downloading', 'preparing'))
            dialog.later.setEnabled(state != 'preparing')
            dialog.later.setText('Cancel download' if state == 'downloading' else 'Later' if state == 'ready' else 'Close')
            dialog.notes.setVisible(self._update_available is not None)
            dialog.progress.setVisible(state in ('downloading', 'preparing'))
            dialog.progress.setRange(0, 0 if state == 'preparing' else 100)
            if state == 'downloading':
                dialog.progress.setValue(0)

    def _update_primary(self):
        if self._update_state == 'available':
            self._downloaded_update = None
            self._show_update_state('downloading')
            self._update_client.download(self._update_available)
        elif self._update_state == 'ready':
            self.install_update()
        elif self._update_state == 'check':
            self.check_for_updates()

    def _update_progress(self, percent):
        if self._update_dialog is not None:
            self._update_dialog.progress.setValue(percent)

    def _update_downloaded(self, path):
        self._downloaded_update = Path(path)
        self._show_update_state('ready')

    def _update_failed(self, message):
        self._show_update_state('available' if self._update_available else 'check', message)

    def _update_cancelled(self):
        self._show_update_state('available' if self._update_available else 'check', 'Update cancelled. Your current app and meetings are kept.')

    @staticmethod
    def _supports_update_installation():
        return os.name == 'nt'

    def install_update(self):
        if not self._supports_update_installation():
            if self._update_available:
                QDesktopServices.openUrl(QUrl(self._update_available.page_url))
            return
        if self._is_busy() or self.record_timer.isActive():
            self._show_update_state('ready', 'Finish the current recording or task before installing the update.')
            return
        if not self._downloaded_update or not self._update_available or not self.persist():
            return
        update, path = self._update_available, self._downloaded_update
        if path.parent.resolve() != (self.store.root / 'updates').resolve():
            self._update_failed('The update file is not in the download folder. Please download it again.')
            return
        self._update_install_active = True
        self._update_install_path = None
        self._show_update_state('preparing')
        def prepare():
            verify_installer(path, update)
            self.store.backup_database()
            return path
        worker = OperationWorker(prepare, self)
        self._update_install_worker = worker
        worker.done.connect(lambda result: setattr(self, '_update_install_path', result))
        worker.failed.connect(lambda message: self._show_update_state('ready', 'The update could not be prepared. Your meetings are kept. Check disk space and try again.'))
        worker.finished.connect(self._update_prepared)
        worker.start()
        self.update_actions()

    def _update_prepared(self):
        self._update_install_active = False
        self.update_actions()
        if self._update_install_path is None:
            return
        try:
            self._launch_update_installer(self._update_install_path)
        except OSError:
            self._show_update_state('ready', 'The installer could not open. Your meetings are kept. Please try again.')
            return
        self._closing_for_update = True
        self.close()

    @staticmethod
    def _launch_update_installer(path):
        subprocess.Popen([str(path)], shell=False)

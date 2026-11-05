"""SolScribe desktop entry point."""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog
from PySide6.QtCore import QLockFile
from PySide6.QtGui import QFont, QIcon
from solscribe.ui import MainWindow
from solscribe.storage import data_dir
from solscribe.backups import restore_archive, restore_database


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('SolScribe')
    app.setOrganizationName('SolScribe')
    if app.style().objectName().lower() != 'fusion':
        app.setStyle('Fusion')
    resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    icon = resources / 'assets' / 'solscribe.ico'
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    font = QFont('Segoe UI', 10)
    app.setFont(font)
    if '--speech-smoke' in sys.argv:
        from solscribe.diagnostics import speech_smoke
        index = sys.argv.index('--speech-smoke')
        speech_smoke(sys.argv[index + 1], 'speech-packaged-metrics.json', '.smoke-models')
        return 0
    if '--update-smoke' in sys.argv:
        from solscribe.update_diagnostics import update_smoke
        update_smoke('update-packaged-metrics.json')
        return 0
    root = None
    try:
        root = data_dir()
        profile_lock = QLockFile(str(root / 'SolScribe.lock'))
        profile_lock.setStaleLockTime(0)
        if not profile_lock.tryLock(0):
            message = QMessageBox()
            message.setWindowTitle('SolScribe is already open')
            message.setText('Please use the existing SolScribe window for this meeting library.')
            message.exec()
            return 0
        window = MainWindow()
    except Exception as exc:
        message = QMessageBox()
        message.setIcon(QMessageBox.Warning)
        message.setWindowTitle('SolScribe could not open')
        message.setText('Please check available disk space and access to your saved files, then try opening SolScribe again.')
        message.setDetailedText(str(exc))
        restore_button = message.addButton('Restore a backup…', QMessageBox.ActionRole)
        restore_button.setEnabled(root is not None)
        message.addButton(QMessageBox.Close)
        message.exec()
        if root is None or message.clickedButton() != restore_button:
            return 1
        source, _ = QFileDialog.getOpenFileName(None, 'Recover meeting library', str(root / 'backups'), 'SolScribe backup (*.db *.zip)')
        if not source or QMessageBox.question(None, 'Recover from this backup?',
            'Replace the meeting database with this backup? The previous database will be preserved. DB-only backups do not contain audio files.',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No) != QMessageBox.Yes:
            return 1
        try:
            operation = restore_database if Path(source).suffix.lower() == '.db' else restore_archive
            operation(root, Path(source))
            window = MainWindow()
        except Exception as recovery_error:
            message.setText('This backup could not be restored. Your previous files have been kept.')
            message.setDetailedText(str(recovery_error))
            message.exec()
            return 1
    window.show()
    if '--smoke-test' in sys.argv:
        from faster_whisper import WhisperModel  # Verify the bundled speech engine imports.
        original_theme = window.theme_name
        for theme in ('light', 'dark'):
            window.set_theme(theme)
            app.processEvents()
            if not window.transcript_stack.isVisible() or window.transcript_stack.height() < 160:
                raise RuntimeError('Meeting workspace is not visible in the packaged application')
        window.load_demo()
        app.processEvents()
        if not window.table.isVisible() or window.table.viewport().height() < 160:
            raise RuntimeError('Transcript rows are not visible in the packaged application')
        window.set_theme(original_theme)
        if window.credit_label.text() != 'zibah@2026':
            raise RuntimeError('App footer is missing')
        window.show_quick_guide()
        for _ in range(3):
            window._guide.next()
            app.processEvents()
        if window._guide.currentId() != 3:
            raise RuntimeError('Packaged setup guide is incomplete')
        window._guide.reject()
        window.close()
        return 0
    window.start_first_run()
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())

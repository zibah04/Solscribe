"""SolScribe desktop entry point."""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QFont, QIcon
from solscribe.ui import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('SolScribe')
    app.setOrganizationName('SolScribe')
    app.setStyle('Fusion')
    resources = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent))
    icon = resources / 'assets' / 'solscribe.ico'
    if icon.is_file():
        app.setWindowIcon(QIcon(str(icon)))
    font = QFont('Segoe UI', 10)
    app.setFont(font)
    try:
        window = MainWindow()
    except Exception as exc:
        message = QMessageBox()
        message.setIcon(QMessageBox.Warning)
        message.setWindowTitle('SolScribe could not open')
        message.setText('Please check available disk space and access to your saved files, then try opening SolScribe again.')
        message.setDetailedText(str(exc))
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
        window.close()
        return 0
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())

"""SolScribe desktop entry point."""
import sys
from pathlib import Path
from PySide6.QtWidgets import QApplication
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
    window = MainWindow()
    window.show()
    if '--smoke-test' in sys.argv:
        from faster_whisper import WhisperModel  # Verify the bundled speech engine imports.
        app.processEvents()
        if not window.table.isVisible() or window.table.viewport().height() < 160:
            raise RuntimeError('Transcript is not visible in the packaged application')
        window.close()
        return 0
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())

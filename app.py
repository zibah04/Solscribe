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
    return app.exec()


if __name__ == '__main__':
    raise SystemExit(main())

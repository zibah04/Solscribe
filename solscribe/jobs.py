"""Small Qt adapters for background operations; domain functions remain Qt-free."""
from PySide6.QtCore import QThread, Signal


class OperationWorker(QThread):
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.done.emit(self.operation())
        except Exception as exc:
            self.failed.emit(f'{type(exc).__name__}: {exc}')

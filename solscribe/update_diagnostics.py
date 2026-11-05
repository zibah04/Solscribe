"""Opt-in real HTTPS update verification; test files are never executed."""
import json
import tempfile
import time
from pathlib import Path
from PySide6.QtCore import QCoreApplication, QTimer
from .update_transport import UpdateClient
from .updates import verify_installer


def update_smoke(output):
    app = QCoreApplication.instance() or QCoreApplication([])
    with tempfile.TemporaryDirectory(prefix='solscribe-update-smoke-') as directory:
        client = UpdateClient(Path(directory), 'v0.3.0', app)
        errors, result = [], {}
        started = time.perf_counter()
        def checked(update):
            if update is None:
                failed('No published update was found for the older verification version')
                return
            result['tag'] = update.tag
            result['bytes'] = update.size
            result['sha256'] = update.sha256
            result['check_seconds'] = time.perf_counter() - started
            result['update'] = update
            client.download(update)
        def downloaded(path):
            try:
                verify_installer(path, result.pop('update'))
            except (OSError, ValueError):
                failed('Downloaded installer failed independent verification')
                return
            result['verified'] = True
            result['total_seconds'] = time.perf_counter() - started
            result['scope'] = 'Real public HTTPS metadata and installer download; installer verified but not executed.'
            app.quit()
        def failed(message):
            errors.append(message)
            client.cancel()
            app.quit()
        client.checked.connect(checked)
        client.downloaded.connect(downloaded)
        client.failed.connect(failed)
        deadline = QTimer(app)
        deadline.setSingleShot(True)
        deadline.timeout.connect(lambda: failed('Update integration check exceeded 180 seconds'))
        deadline.start(180000)
        QTimer.singleShot(0, client.check)
        app.exec()
        deadline.stop()
        client.cancel()
        client.deleteLater()
        result.pop('update', None)
        result['errors'] = errors
        Path(output).write_text(json.dumps(result, indent=2), encoding='utf-8')
        if errors or not result.get('verified'):
            raise RuntimeError('Real update verification failed: ' + '; '.join(errors))
        return result

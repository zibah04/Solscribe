"""Resource policy shared by live and final speech recognition."""
import gc
import os
import logging


def cpu_threads() -> int:
    return max(1, min(4, (os.cpu_count() or 2) - 1))


def release_model(model) -> None:
    native = getattr(model, 'model', None)
    unload = getattr(native, 'unload_model', None)
    if callable(unload):
        try:
            unload()
        except Exception as exc:
            # Cleanup must not mask the original result or failure. No source
            # speech, path, or model-server response is written to logs.
            logging.getLogger(__name__).warning('Speech model cleanup failed (%s)', type(exc).__name__)
    gc.collect()

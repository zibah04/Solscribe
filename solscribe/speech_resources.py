"""Resource policy shared by live and final speech recognition."""
import gc
import os


def cpu_threads() -> int:
    return max(1, min(4, (os.cpu_count() or 2) - 1))


def release_model(model) -> None:
    native = getattr(model, 'model', None)
    unload = getattr(native, 'unload_model', None)
    if callable(unload):
        unload()
    gc.collect()

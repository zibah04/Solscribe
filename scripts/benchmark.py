"""Reproducible, synthetic workload measurements; never a hardware-capture test."""
import argparse
import ctypes
import json
import os
import platform
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path
from types import SimpleNamespace

started = time.perf_counter()
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def rss_bytes():
    if os.name == 'nt':
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in ('peak_working', 'working', 'peak_paged', 'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi = ctypes.WinDLL('psapi', use_last_error=True)
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return counters.working
    return int(Path('/proc/self/statm').read_text().split()[1]) * os.sysconf('SC_PAGE_SIZE')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='performance.json')
    parser.add_argument('--rows', type=int, default=10000)
    args = parser.parse_args()
    import numpy as np
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication
    from solscribe import ui, __version__
    from solscribe.repository import Store
    from solscribe.audio import AudioPacket
    from solscribe.captioning import CaptionEngine
    from solscribe.reports import draft_local
    with tempfile.TemporaryDirectory(prefix='solscribe-benchmark-') as directory:
        root = Path(directory)
        ui.Store = lambda: Store(root / 'data')
        ui.QSettings = lambda *unused: QSettings(str(root / 'settings.ini'), QSettings.IniFormat)
        ui.MicrophoneRecorder.devices = staticmethod(lambda: [])
        ui.SystemLoopbackRecorder.devices = staticmethod(lambda: [])
        app = QApplication.instance() or QApplication([])
        window = ui.MainWindow()
        window.show()
        app.processEvents()
        cpu = platform.processor()
        if not cpu and Path('/proc/cpuinfo').is_file():
            cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')), '')
        if os.name == 'nt':
            class MemoryStatus(ctypes.Structure):
                _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ('total', 'available', 'total_page', 'avail_page', 'total_virtual', 'avail_virtual', 'extended')]
            memory = MemoryStatus()
            memory.length = ctypes.sizeof(memory)
            if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
                raise ctypes.WinError()
            ram = memory.total
        else:
            ram = os.sysconf('SC_PHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')
        result = {'version': __version__, 'os': platform.platform(), 'python': platform.python_version(),
                  'architecture': platform.machine(), 'cpu': cpu, 'logical_cpus': os.cpu_count(), 'physical_ram_bytes': ram,
                  'scope': 'Synthetic local data, offscreen UI; no speech model, disk microphone, or physical-device latency.',
                  'startup_imports_and_first_window_s': round(time.perf_counter() - started, 4), 'idle_rss_bytes': rss_bytes()}
        segments = [{'start': i * 3, 'end': i * 3 + 2, 'speaker': 'Alice',
                     'text': f'Planning point {i}. Alice will prepare the review by Friday.'} for i in range(args.rows)]
        window.store.update(window.session_id, segments=segments)
        began = time.perf_counter()
        window.load_session(window.session_id)
        app.processEvents()
        result['transcript_rows'] = args.rows
        result['load_and_render_s'] = round(time.perf_counter() - began, 4)
        result['loaded_rss_bytes'] = rss_bytes()
        began = time.perf_counter()
        draft_local(window.store.get(window.session_id))
        result['quick_notes_s'] = round(time.perf_counter() - began, 4)
        began = time.perf_counter()
        assert window.persist()
        result['persist_all_rows_s'] = round(time.perf_counter() - began, 4)
        window.close()
        class FakeRecognizer:
            def transcribe(self, audio, **kwargs):
                return iter([SimpleNamespace(start=0, end=len(audio) / 16000, text='Test words')]), None
        engine = CaptionEngine(FakeRecognizer())
        raw = np.full(32000, 500, dtype=np.int16).tobytes()
        tracemalloc.start()
        began = time.perf_counter()
        for chunk in range(2700):  # 90 minutes on the source clock, processed as fast as possible.
            engine.accept(AudioPacket(raw, 16000, chunk * 32000))
        engine.finish()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        result['synthetic_90min_stream'] = {'source_seconds': engine.processed_seconds,
            'wall_s': round(time.perf_counter() - began, 4), 'traced_current_bytes': current,
            'traced_peak_bytes': peak, 'retained_context_frames': len(engine.context),
            'sampled_processing_windows': len(engine.processing_times), 'recognizer': 'FakeRecognizer; buffer retention only'}
        Path(args.output).write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

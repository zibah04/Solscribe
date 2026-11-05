"""Pure NumPy utilities for real-time audio chunking and downsampling."""
from __future__ import annotations

import numpy as np
from collections import deque
from .audio import Decimator48k

class PCMChunker:
    """Incremental 16/48 kHz mono PCM16 -> contiguous 16 kHz float32 windows.

    At 48 kHz use a stateful low-pass FIR before decimation. Keep sample phase
    across packets so irregular buffer lengths do not introduce clock drift.
    """
    OUTPUT_RATE = 16000

    def __init__(self, chunk_seconds=6.0):
        if not 1 <= chunk_seconds <= 30:
            raise ValueError('Chunk duration must be between 1 and 30 seconds')
        self.chunk_size = int(chunk_seconds * self.OUTPUT_RATE)
        self._samples = deque()
        self._sample_count = 0
        self._emitted = 0
        self._resampler = Decimator48k()

    def feed(self, raw: bytes, rate: int):
        if not raw:
            return []
        samples = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
        if rate == 48000:
            samples = self._resampler.feed(samples)
        elif rate != 16000:
            raise ValueError('Live transcription only supports 16 kHz mic and 48 kHz PC audio')
        if samples.size:
            self._samples.append(samples)
            self._sample_count += len(samples)
        result = []
        while self._sample_count >= self.chunk_size:
            result.append(self._pop(self.chunk_size))
        return result

    def _pop(self, count):
        parts = []
        remaining = count
        while remaining > 0:
            part = self._samples.popleft()
            if len(part) <= remaining:
                parts.append(part)
                remaining -= len(part)
            else:
                parts.append(part[:remaining])
                self._samples.appendleft(part[remaining:])
                remaining = 0
        self._sample_count -= count
        start = self._emitted / self.OUTPUT_RATE
        self._emitted += count
        return start, np.concatenate(parts)

    def flush(self, minimum_seconds=0.7):
        if self._sample_count >= int(self.OUTPUT_RATE * minimum_seconds):
            return self._pop(self._sample_count)
        return None


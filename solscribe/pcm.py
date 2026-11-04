"""Pure NumPy utilities for real-time audio chunking and downsampling."""
from __future__ import annotations

import numpy as np

class PCMChunker:
    """Incremental 16/48 kHz mono PCM16 -> contiguous 16 kHz float32 windows.

    At 48 kHz downsample each group of 3 with a basic anti-aliasing box filter.
    Keep the 1–2-sample remainder between packets to prevent clock drift.
    """
    OUTPUT_RATE = 16000

    def __init__(self, chunk_seconds=6.0):
        if not 1 <= chunk_seconds <= 30:
            raise ValueError('Chunk duration must be between 1 and 30 seconds')
        self.chunk_size = int(chunk_seconds * self.OUTPUT_RATE)
        self._samples = []
        self._sample_count = 0
        self._emitted = 0
        self._carry_48k = np.empty(0, dtype=np.float32)

    def feed(self, raw: bytes, rate: int):
        if not raw:
            return []
        samples = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
        if rate == 48000:
            if self._carry_48k.size:
                samples = np.concatenate((self._carry_48k, samples))
            n = (len(samples) // 3) * 3
            self._carry_48k = samples[n:].copy()
            samples = samples[:n].reshape(-1, 3).mean(axis=1)
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
            part = self._samples.pop(0)
            if len(part) <= remaining:
                parts.append(part)
                remaining -= len(part)
            else:
                parts.append(part[:remaining])
                self._samples.insert(0, part[remaining:])
                remaining = 0
        self._sample_count -= count
        start = self._emitted / self.OUTPUT_RATE
        self._emitted += count
        return start, np.concatenate(parts)

    def flush(self, minimum_seconds=0.7):
        if self._sample_count >= int(self.OUTPUT_RATE * minimum_seconds):
            return self._pop(self._sample_count)
        return None


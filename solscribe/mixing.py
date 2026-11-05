"""Bounded software-clock mixer. No audio devices, file I/O or Qt dependencies."""
from __future__ import annotations
import math
import numpy as np
from .audio import AudioPacket


class TimelineMixer:
    RATE = 16000
    BLOCK = 1024

    def __init__(self, sources=('microphone', 'system'), max_buffer_seconds=4):
        self.sources = tuple(sources)
        self.blocks = {}
        self.position = 0
        self.latest = 0
        self.max_frames = int(max_buffer_seconds * self.RATE)
        self.late_frames = 0

    def push(self, source: str, samples: np.ndarray, start_seconds: float, end_seconds: float):
        if source not in self.sources or not math.isfinite(start_seconds) or not math.isfinite(end_seconds):
            raise ValueError('Invalid source or audio clock')
        if not samples.size or end_seconds <= start_seconds:
            return
        # A shared monotonic interval handles source offset and gradual clock
        # drift; interpolate onto one common 16 kHz timeline after anti-aliasing.
        first, last = round(start_seconds * self.RATE), round(end_seconds * self.RATE)
        if last <= self.position:
            self.late_frames += max(0, last - first)
            return
        begin = max(first, self.position, 0)
        if begin > first:
            self.late_frames += begin - first
        stop = min(last, self.position + self.max_frames)
        if last > stop:
            raise BufferError('Source is too far ahead of the mixer clock')
        points = (np.arange(begin, stop) - first) * len(samples) / max(1, last - first)
        aligned = np.interp(points, np.arange(len(samples)), samples).astype(np.float32)
        for offset in range(begin // self.BLOCK, (stop + self.BLOCK - 1) // self.BLOCK):
            base = offset * self.BLOCK
            left, right = max(begin, base), min(stop, base + self.BLOCK)
            if right <= left:
                continue
            tracks = self.blocks.setdefault(offset, {})
            track, present = tracks.setdefault(source, (np.zeros(self.BLOCK, np.float32), np.zeros(self.BLOCK, bool)))
            track[left-base:right-base] = aligned[left-begin:right-begin]
            present[left-base:right-base] = True
        self.latest = max(self.latest, last)

    def drain(self, until_seconds: float, *, final=False) -> list[AudioPacket]:
        limit = min(round(max(0, until_seconds) * self.RATE), self.latest if final else self.position + self.max_frames)
        result = []
        while self.position + self.BLOCK <= limit or (final and self.position < limit):
            count = min(self.BLOCK, limit - self.position)
            tracks = self.blocks.pop(self.position // self.BLOCK, {})
            mix, contributors = np.zeros(self.BLOCK, np.float32), np.zeros(self.BLOCK, np.int16)
            for values, present in tracks.values():
                mix += values
                contributors += present
            mix /= np.maximum(contributors, 1)
            raw = (np.clip(mix[:count], -1, 1) * 32767).astype('<i2').tobytes()
            result.append(AudioPacket(raw, self.RATE, self.position))
            self.position += count
        return result

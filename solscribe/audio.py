"""Capture-clock packets, bounded live delivery and streaming anti-alias filtering."""
from __future__ import annotations
from dataclasses import dataclass
import queue
import numpy as np


@dataclass(frozen=True)
class AudioPacket:
    pcm: bytes
    sample_rate: int
    start_frame: int
    capture_time: float | None = None

    @property
    def start_seconds(self) -> float:
        return self.start_frame / self.sample_rate

    @property
    def frames(self) -> int:
        return len(self.pcm) // 2


def deliver_live(target, packet: AudioPacket) -> int:
    """Keep recent audio when full; never wait for speech recognition."""
    if target is None:
        return 0
    try:
        target.put_nowait(packet)
        return 0
    except queue.Full:
        dropped = 0
        try:
            previous = target.get_nowait()
            dropped = previous.frames if isinstance(previous, AudioPacket) else len(previous[0]) // 2
        except queue.Empty:
            pass
        try:
            target.put_nowait(packet)
        except queue.Full:
            dropped += packet.frames
        return dropped


class Decimator48k:
    """63-tap low-pass FIR and 3:1 decimation with state across every packet.

    The causal filter delay is 31/48000 seconds (<0.65 ms). Initial edge extension
    avoids an artificial fade-in. Output counts and phase do not depend on packet
    size. No SciPy dependency or heavyweight resampler is needed.
    """
    def __init__(self):
        index = np.arange(63, dtype=np.float64) - 31
        normalized = 7000 / 48000
        self.taps = 2 * normalized * np.sinc(2 * normalized * index) * np.hamming(63)
        self.taps /= self.taps.sum()
        self.history = None
        self.input_frames = 0

    def feed(self, samples: np.ndarray) -> np.ndarray:
        if not samples.size:
            return np.empty(0, dtype=np.float32)
        if self.history is None:
            self.history = np.full(62, samples[0], dtype=np.float32)
        joined = np.concatenate((self.history, samples))
        filtered = np.convolve(joined, self.taps, mode='valid')
        first = (2 - self.input_frames) % 3
        output = filtered[first::3].astype(np.float32)
        self.history = joined[-62:].copy()
        self.input_frames += len(samples)
        return output

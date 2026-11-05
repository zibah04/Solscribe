"""Repair only known, application-owned PCM WAV recordings after interruption."""
from __future__ import annotations
import os
from pathlib import Path
import struct


def recover_pcm_wave(path: Path) -> dict:
    """Repair RIFF/data sizes to include complete PCM frames already on disk.

    This does not reconstruct unwritten audio or touch imported media. The caller
    must establish ownership before invoking it. Refuse unfamiliar file layouts.
    """
    path = Path(path)
    size = path.stat().st_size
    if size < 44 or size > 0xFFFFFFFF:
        raise ValueError('Unsupported or incomplete WAV header')
    with path.open('r+b') as stream:
        if stream.read(4) != b'RIFF':
            raise ValueError('Not a PCM RIFF recording')
        stream.seek(8)
        if stream.read(4) != b'WAVE':
            raise ValueError('Not a WAVE recording')
        position, fmt, data_header = 12, None, None
        while position + 8 <= size:
            stream.seek(position)
            chunk, length = struct.unpack('<4sI', stream.read(8))
            if chunk == b'fmt ':
                if length < 16 or length > 4096:
                    raise ValueError('Invalid PCM format')
                fmt = struct.unpack('<HHIIHH', stream.read(16))
            elif chunk == b'data':
                data_header = position
                break
            position += 8 + length + length % 2
        if fmt is None or data_header is None:
            raise ValueError('Missing PCM format/data header')
        encoding, channels, rate, _, alignment, bits = fmt
        if encoding != 1 or channels not in (1, 2) or bits != 16 or alignment != channels * 2:
            raise ValueError('Recording is not supported PCM16')
        if rate not in (16000, 48000):
            raise ValueError('Unexpected capture sample rate')
        available = size - data_header - 8
        audio_bytes = available - available % alignment
        stream.truncate(data_header + 8 + audio_bytes)
        stream.seek(4)
        stream.write(struct.pack('<I', data_header + audio_bytes))
        stream.seek(data_header + 4)
        stream.write(struct.pack('<I', audio_bytes))
        stream.flush()
        os.fsync(stream.fileno())
    return {'frames': audio_bytes // alignment, 'sample_rate': rate,
            'duration': audio_bytes / alignment / rate}

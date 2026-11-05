"""Qt-independent, capture-clock live caption engine with overlapping context."""
from __future__ import annotations
from collections import deque
import re
import time
import numpy as np
from .audio import AudioPacket
from .pcm import PCMChunker


class CaptionEngine:
    def __init__(self, model, language=None, *, chunk_seconds=2.0, overlap_seconds=1.0, notify=lambda text: None):
        self.model, self.language = model, language
        self.chunk_seconds = chunk_seconds
        self.overlap_frames = int(min(overlap_seconds, chunk_seconds / 2) * 16000)
        self.notify = notify
        self.chunker = PCMChunker(chunk_seconds)
        self.origin = 0.0
        self.expected = 0.0
        self.processed_seconds = 0.0
        self.skipped_seconds = 0.0
        self.context = np.empty(0, dtype=np.float32)
        self.previous_text = ''
        self.processing_times = deque(maxlen=256)
        self._rate = None

    def accept(self, packet: AudioPacket) -> list[dict]:
        if packet.sample_rate not in (16000, 48000) or len(packet.pcm) % 2 or packet.start_frame < 0:
            raise ValueError('Invalid capture packet')
        start = packet.start_seconds
        if start < self.expected - 1 / packet.sample_rate:
            raise ValueError('Capture packets arrived out of order')
        output = []
        if abs(start - self.expected) > 1 / packet.sample_rate or (self._rate is not None and self._rate != packet.sample_rate):
            output.extend(self.finish())
            self.skipped_seconds += max(0.0, start - self.expected)
            self.origin = start
            self.chunker = PCMChunker(self.chunk_seconds)
            self.context = np.empty(0, dtype=np.float32)
            self.previous_text = ''
            self.notify(f'Live words skipped {self.skipped_seconds:.1f}s of audio. Your recording is kept; improve the transcript after stopping.')
        self._rate = packet.sample_rate
        self.expected = start + packet.frames / packet.sample_rate
        for piece in self.chunker.feed(packet.pcm, packet.sample_rate):
            output.extend(self._infer(piece))
        return output

    def finish(self) -> list[dict]:
        piece = self.chunker.flush(minimum_seconds=.05)
        return self._infer(piece) if piece is not None else []

    def _infer(self, piece) -> list[dict]:
        local_start, fresh = piece
        start = self.origin + local_start
        end = start + len(fresh) / 16000
        if not fresh.size or float(np.sqrt(np.mean(fresh * fresh))) < .0003:
            self.processed_seconds = end
            self.context = np.empty(0, dtype=np.float32)
            return []
        overlap = len(self.context) / 16000
        audio = np.concatenate((self.context, fresh)) if self.context.size else fresh
        offset = start - overlap
        self.notify('Writing down what you said…')
        began = time.perf_counter()
        iterator, _ = self.model.transcribe(audio, language=self.language, beam_size=1, best_of=1,
                                           word_timestamps=True, vad_filter=True,
                                           condition_on_previous_text=False, temperature=0.0,
                                           no_speech_threshold=.5)
        result = []
        for part in iterator:
            text = (part.text or '').strip()
            part_start, part_end = offset + float(part.start), min(end, offset + float(part.end))
            if not text or part_end <= start + .001:
                continue
            words = getattr(part, 'words', None)
            if words:
                current = [word for word in words if offset + (float(word.start) + float(word.end)) / 2 >= start - .01]
                if not current:
                    continue
                text = ''.join(word.word for word in current).strip()
                part_start = max(start, offset + float(current[0].start))
                part_end = min(end, offset + float(current[-1].end))
            elif part_start < start and self.previous_text:
                # Conservative fallback for recognizers without word alignment.
                # Never remove a complete repeated utterance just on text match.
                tokens = text.split()
                previous = self.previous_text.split()
                normal = lambda word: re.sub(r'\W', '', word).casefold()
                for count in range(min(len(tokens) - 1, len(previous), 20), 0, -1):
                    if list(map(normal, previous[-count:])) == list(map(normal, tokens[:count])):
                        text = ' '.join(tokens[count:])
                        break
            if text:
                result.append({'start': round(max(start, part_start), 3),
                               'end': round(max(start, part_end), 3), 'speaker': 'Speaker', 'text': text})
        self.processing_times.append(time.perf_counter() - began)
        self.previous_text = ' '.join(item['text'] for item in result)[-1200:]
        self.context = audio[-self.overlap_frames:].copy() if self.overlap_frames else np.empty(0, dtype=np.float32)
        self.processed_seconds = end
        self.notify('Listening · live words are provisional. You can improve them after recording.')
        return result

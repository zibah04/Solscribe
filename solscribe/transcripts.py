"""Transcript validation, speaker operations and non-destructive refinement."""
from __future__ import annotations
import copy
import math


def validate_segments(segments: list) -> list[dict]:
    if not isinstance(segments, list):
        raise ValueError('Transcript must be a list of timed segments')
    result = []
    for segment in segments:
        if not isinstance(segment, dict) or not isinstance(segment.get('text'), str):
            raise ValueError('Invalid transcript segment')
        start, end = float(segment.get('start', 0)), float(segment.get('end', 0))
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end < start:
            raise ValueError('Invalid transcript timestamp')
        speaker = segment.get('speaker') or 'Speaker'
        if not isinstance(speaker, str) or len(speaker) > 200:
            raise ValueError('Invalid speaker label')
        result.append({**segment, 'start': start, 'end': end, 'speaker': speaker})
    return result


def preserve_speakers(previous: list[dict], candidate: list[dict]) -> list[dict]:
    """Transfer existing manual labels by time overlap, never infer real identity."""
    previous, candidate = validate_segments(previous), validate_segments(candidate)
    output = []
    cursor = 0
    for part in candidate:
        while cursor < len(previous) and previous[cursor]['end'] <= part['start']:
            cursor += 1
        scores = {}
        for old in previous[cursor:]:
            if old['start'] >= part['end']:
                break
            overlap = max(0, min(old['end'], part['end']) - max(old['start'], part['start']))
            if overlap:
                scores[old['speaker']] = scores.get(old['speaker'], 0) + overlap
        item = copy.deepcopy(part)
        if scores:
            ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
            # Ambiguous boundaries keep a generic label rather than assigning
            # one participant's name to words spoken by several people.
            if len(ordered) == 1 or ordered[0][1] > 1.5 * ordered[1][1]:
                item['speaker'] = ordered[0][0]
        output.append(item)
    return output


def rename_speaker(segments: list[dict], old: str, new: str) -> list[dict]:
    if not new.strip() or len(new.strip()) > 200:
        raise ValueError('Enter a speaker name with at most 200 characters')
    return [{**segment, 'speaker': new.strip() if segment.get('speaker') == old else segment.get('speaker', 'Speaker')}
            for segment in validate_segments(segments)]

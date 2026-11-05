import time
from pathlib import Path
from types import SimpleNamespace
import wave
import numpy as np
import pytest

from test_live_ui import app, window
from solscribe.audio import AudioPacket
from solscribe.combined import CombinedRecorder
from solscribe.mixing import TimelineMixer
from solscribe.transcripts import preserve_speakers, validate_segments


def read(path):
    with wave.open(str(path), 'rb') as audio:
        return np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').copy(), audio.getframerate()


class Source:
    RATE = 16000
    def __init__(self):
        self.path = None
        self.frames = 0
        self.active = False
        self.level = .25
        self.error = None
        self.live_dropped = 0
        self.live_queue = None
        self.started_at = 0
    def start(self, path, device=None):
        self.path = Path(path)
        self.started_at = time.perf_counter()
        self.frames = self.RATE
        raw = np.full(self.RATE, 8000, dtype='<i2').tobytes()
        with wave.open(str(path), 'wb') as audio:
            audio.setnchannels(1); audio.setsampwidth(2); audio.setframerate(self.RATE); audio.writeframes(raw)
        self.live_queue.put_nowait(AudioPacket(raw, self.RATE, 0, self.started_at))
        self.active = True
    def stop(self):
        self.active = False
        return self.path


def test_combined_capture_keeps_two_originals_and_a_valid_mix(tmp_path):
    class System(Source): RATE = 48000
    recorder = CombinedRecorder(Source, System)
    recorder.start(tmp_path / 'mixed.wav')
    recorder.stop()
    mixed, rate = read(recorder.path)
    assert rate == 16000 and 16000 <= len(mixed) < 17000
    assert 7400 < mixed[1000:15000].mean() < 8500
    assert set(recorder.source_tracks) == {'microphone', 'system'}
    for track in recorder.source_tracks.values():
        assert Path(track['path']).is_file() and track['offset'] >= 0
    assert read(recorder.source_tracks['system']['path'])[1] == 48000
    assert not recorder.active and not recorder.thread.is_alive()


def test_failed_source_does_not_destroy_the_other_source(tmp_path):
    class Failed(Source):
        def start(self, *args, **kwargs):
            self.error = 'device unavailable'
            raise OSError(self.error)
    recorder = CombinedRecorder(Source, Failed)
    recorder.start(tmp_path / 'mixed.wav')
    recorder.stop()
    mixed, _ = read(recorder.path)
    assert mixed[1000:15000].mean() > 7000
    assert 'system' in recorder.error
    assert 'microphone' in recorder.source_tracks


def test_mixer_aligns_source_offsets_and_does_not_clip():
    mixer = TimelineMixer()
    signal = np.zeros(16000, np.float32)
    signal[8000] = 1
    mixer.push('microphone', signal, 0, 1)
    mixer.push('system', signal, .25, 1.25)
    output = np.frombuffer(b''.join(p.pcm for p in mixer.drain(1.25, final=True)), dtype='<i2') / 32768
    assert np.flatnonzero(output > .2).tolist() == [8000, 12000]
    assert np.max(np.abs(output)) <= 1


def test_drift_is_resampled_to_shared_clock_without_unbounded_buffers():
    mixer = TimelineMixer()
    tone = np.sin(np.arange(32000) * 2 * np.pi * 10 / 16000).astype(np.float32)
    mixer.push('microphone', tone, 0, 2)
    mixer.push('system', tone, 0, 2.002)
    output = mixer.drain(2.002, final=True)
    assert sum(packet.frames for packet in output) == 32032
    assert not mixer.blocks


def test_late_audio_is_counted_without_rewriting_saved_mix():
    mixer = TimelineMixer()
    mixer.push('microphone', np.ones(16000, np.float32), 0, 1)
    mixer.drain(1, final=True)
    mixer.push('system', np.ones(16000, np.float32), 0, 1)
    assert mixer.late_frames == 16000 and not mixer.blocks


def test_manual_speaker_labels_transfer_only_when_timing_is_clear():
    previous = [{'start': 0, 'end': 2, 'speaker': 'Alice', 'text': 'Old words'},
                {'start': 2, 'end': 4, 'speaker': 'Bob', 'text': 'Other words'}]
    candidate = [{'start': 0, 'end': 1.5, 'text': 'Improved words'},
                 {'start': 1, 'end': 3, 'text': 'Ambiguous boundary'}]
    output = preserve_speakers(previous, candidate)
    assert output[0]['speaker'] == 'Alice'
    assert output[1]['speaker'] == 'Speaker'
    assert previous[0]['text'] == 'Old words'


def test_declining_improved_words_keeps_corrections_and_notes(window, monkeypatch):
    window.load_demo()
    sid = window.session_id
    window.table.item(0, 1).setText('Alice')
    window.doc_edits['Minutes'].setPlainText('Reviewed notes')
    window.persist()
    before = window.store.get(sid)
    window._transcription_session_id = sid
    monkeypatch.setattr(window, 'review_transcript', lambda *args: False)
    window._transcribed({'segments': [{'start': 2, 'end': 9, 'text': 'New words'}]})
    after = window.store.get(sid)
    assert after['segments'] == before['segments'] and after['minutes'] == 'Reviewed notes'


def test_accepting_improved_words_keeps_notes_speakers_and_history(window, monkeypatch):
    window.load_demo()
    sid = window.session_id
    window.table.item(0, 1).setText('Alice')
    window.doc_edits['Minutes'].setPlainText('Reviewed notes')
    window.persist()
    window._transcription_session_id = sid
    monkeypatch.setattr(window, 'review_transcript', lambda *args: True)
    window._transcribed({'segments': [{'start': 2, 'end': 9, 'text': 'New words'}]})
    after = window.store.get(sid)
    assert after['segments'][0]['speaker'] == 'Alice'
    assert after['minutes'] == 'Reviewed notes'
    assert after['transcript_history'][-1]['segments'][0]['speaker'] == 'Alice'


@pytest.mark.parametrize('start,end', [(float('nan'), 1), (0, float('inf')), (-1, 2), (3, 1)])
def test_invalid_transcript_times_are_rejected(start, end):
    with pytest.raises(ValueError):
        validate_segments([{'start': start, 'end': end, 'text': 'Invalid'}])

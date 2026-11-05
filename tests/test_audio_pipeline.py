import queue
import time
from types import SimpleNamespace
import numpy as np
import pytest

from solscribe.audio import AudioPacket, Decimator48k, deliver_live
from solscribe.captioning import CaptionEngine
from solscribe.live import LiveTranscriptionWorker


def pcm(seconds=2, amplitude=1000):
    return np.full(int(16000 * seconds), amplitude, dtype=np.int16).tobytes()


class Model:
    def __init__(self, *args, **kwargs): self.calls = 0
    def transcribe(self, audio, **kwargs):
        self.calls += 1
        return iter([SimpleNamespace(start=0, end=len(audio) / 16000, text='Test words')]), None


def test_fir_resampling_rejects_aliases_and_preserves_speech_band():
    t = np.arange(48000) / 48000
    low = Decimator48k().feed(np.sin(2 * np.pi * 1000 * t).astype(np.float32))[200:]
    high = Decimator48k().feed(np.sin(2 * np.pi * 12000 * t).astype(np.float32))[200:]
    assert np.sqrt(np.mean(high ** 2)) < .03 * np.sqrt(np.mean(low ** 2))
    assert np.sqrt(np.mean(low ** 2)) > .65


def test_fir_is_invariant_to_irregular_packet_sizes():
    rng = np.random.default_rng(42)
    samples = rng.normal(0, .1, 48001).astype(np.float32)
    whole = Decimator48k().feed(samples)
    resampler = Decimator48k()
    pieces = [resampler.feed(samples[i:i+997]) for i in range(0, len(samples), 997)]
    np.testing.assert_allclose(np.concatenate(pieces), whole, atol=1e-7)
    assert len(whole) == 16000


def test_live_overflow_keeps_recent_packets_with_original_clock():
    target = queue.Queue(maxsize=2)
    skipped = sum(deliver_live(target, AudioPacket(pcm(1), 16000, i * 16000)) for i in range(5))
    assert skipped == 48000 and target.qsize() == 2
    model = Model()
    engine = CaptionEngine(model, chunk_seconds=1)
    output = engine.accept(target.get_nowait()) + engine.accept(target.get_nowait())
    assert output[0]['start'] == 3
    assert output[-1]['end'] == 5
    assert engine.skipped_seconds == 3


def test_timestamps_do_not_collapse_after_a_gap():
    engine = CaptionEngine(Model())
    first = engine.accept(AudioPacket(pcm(), 16000, 0))
    second = engine.accept(AudioPacket(pcm(), 16000, 5 * 16000))
    assert (first[0]['start'], first[0]['end']) == (0, 2)
    assert (second[0]['start'], second[0]['end']) == (5, 7)
    assert engine.processed_seconds == 7 and engine.skipped_seconds == 3


def test_overlap_reconciles_words_by_their_audio_times():
    class WordModel:
        def __init__(self): self.calls = 0
        def transcribe(self, audio, **kwargs):
            self.calls += 1
            if self.calls == 1:
                words = [SimpleNamespace(start=0, end=.8, word=' Hello'), SimpleNamespace(start=.8, end=1.8, word=' world')]
            else:
                words = [SimpleNamespace(start=0, end=.8, word=' world'), SimpleNamespace(start=1.1, end=1.8, word=' again')]
            return iter([SimpleNamespace(start=0, end=2, text=' '.join(w.word for w in words), words=words)]), None
    engine = CaptionEngine(WordModel())
    first = engine.accept(AudioPacket(pcm(), 16000, 0))
    second = engine.accept(AudioPacket(pcm(), 16000, 32000))
    assert first[0]['text'] == 'Hello world'
    assert second[0]['text'] == 'again'
    assert second[0]['start'] == 2.1


def test_silence_is_skipped_but_quiet_speech_can_be_processed():
    model = Model()
    engine = CaptionEngine(model)
    assert engine.accept(AudioPacket(pcm(amplitude=0), 16000, 0)) == []
    assert model.calls == 0 and engine.processed_seconds == 2
    assert engine.accept(AudioPacket(pcm(amplitude=50), 16000, 32000))
    assert model.calls == 1


def test_final_short_tail_retains_absolute_clock():
    engine = CaptionEngine(Model())
    engine.accept(AudioPacket(pcm(.25), 16000, 10 * 16000))
    tail = engine.finish()
    assert tail[0]['start'] == 10 and tail[0]['end'] == 10.25


def test_long_stream_has_bounded_context_and_metrics():
    engine = CaptionEngine(Model())
    raw = pcm()
    for i in range(500):
        engine.accept(AudioPacket(raw, 16000, i * 32000))
    assert engine.processed_seconds == 1000
    assert engine.context.nbytes <= 16000 * 4
    assert len(engine.processing_times) <= 256
    assert len(engine.previous_text) <= 1200


def test_artificial_processing_delay_is_measured():
    class Slow(Model):
        def transcribe(self, *args, **kwargs):
            time.sleep(.02)
            return super().transcribe(*args, **kwargs)
    engine = CaptionEngine(Slow())
    engine.accept(AudioPacket(pcm(), 16000, 0))
    assert engine.processing_times[-1] >= .02


def test_worker_cancellation_before_loading_avoids_model_download():
    def forbidden(*args, **kwargs):
        pytest.fail('Model should not load after cancellation')
    worker = LiveTranscriptionWorker(queue.Queue(), 'tiny', 'auto', '.', model_factory=forbidden)
    worker.cancel()
    worker.run()


def test_out_of_order_packets_are_rejected():
    engine = CaptionEngine(Model())
    engine.accept(AudioPacket(pcm(), 16000, 32000))
    with pytest.raises(ValueError, match='out of order'):
        engine.accept(AudioPacket(pcm(), 16000, 0))

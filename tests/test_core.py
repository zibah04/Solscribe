from pathlib import Path

from solscribe.storage import Store
from solscribe.reports import transcript_text, draft_local, stamp, _chunks
from solscribe.exporters import export_file, safe_filename, srt_timestamp, srt_text


def test_store_create_update_delete(tmp_path):
    store = Store(tmp_path)
    sid = store.create('Board meeting')
    assert store.get(sid)['title'] == 'Board meeting'
    store.update(sid, attendees='Alice, Bob', segments=[{'start': 0, 'end': 3, 'speaker': 'A', 'text': 'Welcome.'}])
    assert store.get(sid)['attendees'] == 'Alice, Bob'
    assert store.list('board')[0]['segments'][0]['speaker'] == 'A'
    store.delete(sid)
    assert store.get(sid) is None


def test_draft_avoids_fabricated_claims(tmp_path):
    store = Store(tmp_path)
    sid = store.create('Planning')
    store.update(sid, segments=[
        {'start': 0, 'end': 4, 'speaker': 'Speaker', 'text': 'The home page is ready.'},
        {'start': 5, 'end': 10, 'speaker': 'Speaker', 'text': 'We agreed to launch next week.'},
        {'start': 11, 'end': 20, 'speaker': 'Speaker', 'text': 'I will send the invoice by Friday.'},
    ])
    result = draft_local(store.get(sid))
    assert 'We agreed to launch next week' in result['minutes']
    assert 'I will send the invoice' in result['actions']
    assert 'verify' in result['minutes'].lower()
    assert '00:11' in result['actions']
    assert 'Alice' not in result['minutes']


def test_export_multiple_formats(tmp_path):
    session = {'id': '1234', 'title': 'Marketing / Launch',
               'minutes': '# Minutes\n\n## Review\n- **Decision:** Launch approved.',
               'memo': '# Memo\n\nApproved.', 'actions': '# Actions\n\nNone.',
               'segments': [{'start': .25, 'end': 3.123, 'speaker': 'Speaker', 'text': 'Hello team.'}]}
    assert safe_filename(session['title']) == 'Marketing - Launch'
    for fmt in ('docx', 'pdf', 'txt', 'md', 'json'):
        dest = tmp_path / ('test.' + fmt)
        assert export_file(dest, fmt, session) == dest
        assert dest.exists() and dest.stat().st_size > 40
    srt = tmp_path / 'transcript.srt'
    export_file(srt, 'srt', session, 'Transcript')
    assert '00:00:00,250 --> 00:00:03,123' in srt.read_text(encoding='utf-8-sig')


def test_stamp_and_chunks():
    assert stamp(121) == '02:01'
    assert stamp(3700) == '01:01:40'
    assert srt_timestamp(1.0004) == '00:00:01,000'
    assert len(_chunks(['hello '*3000], max_chars=2000)) == 9


def test_recording_cleanup_only_within_managed_folder(tmp_path):
    store = Store(tmp_path / 'store')
    imported = tmp_path / 'original.wav'
    imported.write_bytes(b'FAKE')
    sid = store.create('External', audio_path=str(imported))
    store.delete(sid)
    assert imported.exists()
    owned = store.recordings / 'test.wav'
    owned.write_bytes(b'FAKE')
    sid = store.create('Internal', audio_path=str(owned))
    store.delete(sid)
    assert owned.exists()  # Deletion is recoverable, even inside managed storage.
    assert store.get(sid) is None
    store.restore(sid)
    assert store.get(sid)['audio_path'] == str(owned)


def test_microphone_writes_valid_wave(tmp_path, monkeypatch):
    import sys
    import types
    import wave
    import numpy as np
    from solscribe.recorder import MicrophoneRecorder

    class FakeInput:
        def __init__(self, **kwargs):
            self.callback = kwargs['callback']
        def start(self):
            self.callback(np.full((1024, 1), 1000, dtype=np.int16), 1024, None, None)
        def stop(self):
            pass
        def close(self):
            pass

    monkeypatch.setitem(sys.modules, 'sounddevice', types.SimpleNamespace(InputStream=FakeInput))
    recorder = MicrophoneRecorder()
    path = tmp_path / 'recorded.wav'
    recorder.start(path)
    recorder.stop()
    with wave.open(str(path), 'rb') as wav:
        assert wav.getnframes() == 1024
        assert wav.getframerate() == 16000
        assert wav.getnchannels() == 1
    assert recorder.elapsed > .06


def test_mocked_ollama_json(monkeypatch):
    from solscribe import reports
    monkeypatch.setattr(reports, '_ask_ollama',
        lambda model, prompt, response_json=False: '{"summary":"# Summary", "minutes":"# Minutes", "memo":"# Memo", "actions":"# Actions"}')
    session = {'title': 'Team', 'segments': [{'start': 0, 'end': 3,
               'speaker': 'Speaker', 'text': 'I will email the test report tomorrow.'}]}
    data = reports.draft_ai(session)
    assert data['engine'] == 'Ollama · llama3.2'
    assert data['minutes'] == '# Minutes'


def test_live_pcm_chunker_16k_contiguous_windows():
    import numpy as np
    from solscribe.pcm import PCMChunker
    chunker = PCMChunker(chunk_seconds=2)
    audio = np.full(16000 * 5, 1000, dtype=np.int16)
    windows = []
    for raw in (audio[:7000].tobytes(), audio[7000:65000].tobytes(), audio[65000:].tobytes()):
        windows += chunker.feed(raw, 16000)
    assert len(windows) == 2
    tail = chunker.flush()
    assert tail is not None
    assert [round(start, 2) for start, _ in windows + [tail]] == [0, 2, 4]
    assert [len(buffer) for _, buffer in windows + [tail]] == [32000, 32000, 16000]
    assert all(abs(float(buffer.mean()) - 1000 / 32768) < 1e-6 for _, buffer in windows + [tail])


def test_live_pcm_chunker_48k_resampling_no_drift():
    import numpy as np
    from solscribe.pcm import PCMChunker
    chunker = PCMChunker(chunk_seconds=1)
    audio = np.full(48000 * 3, 2300, dtype=np.int16)
    output = []
    # Irregular packet lengths exercise cross-packet 48 kHz remainder logic.
    for offset in range(0, len(audio), 1024):
        output.extend(chunker.feed(audio[offset:offset + 1024].tobytes(), 48000))
    assert len(output) == 3
    assert chunker.flush() is None
    assert [start for start, _ in output] == [0, 1, 2]
    assert all(len(buffer) == 16000 for _, buffer in output)
    assert abs(float(output[2][1].mean()) - 2300 / 32768) < 1e-6


def test_old_database_migrates_summary_column(tmp_path):
    import sqlite3
    data_root = tmp_path / 'old'
    data_root.mkdir()
    database = data_root / 'solscribe.db'
    with sqlite3.connect(database) as conn:
        conn.execute('''CREATE TABLE sessions (
            id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            title TEXT NOT NULL, audio_path TEXT DEFAULT '', duration REAL DEFAULT 0,
            language TEXT DEFAULT '', model TEXT DEFAULT '', segments TEXT DEFAULT '[]',
            meeting_date TEXT DEFAULT '', attendees TEXT DEFAULT '',
            location TEXT DEFAULT '', chair TEXT DEFAULT '', agenda TEXT DEFAULT '',
            minutes TEXT DEFAULT '', memo TEXT DEFAULT '', actions TEXT DEFAULT '',
            notes TEXT DEFAULT ''
        )''')
    store = Store(data_root)
    sid = store.create('Legacy data')
    store.update(sid, summary='My new summary')
    assert store.get(sid)['summary'] == 'My new summary'


def test_local_summary_and_export(tmp_path):
    store = Store(tmp_path / 'data')
    sid = store.create('Voice note')
    store.update(sid, segments=[{'start': 0, 'end': 2, 'speaker': 'Speaker',
                                 'text': 'I need to email the report.'}])
    summary = draft_local(store.get(sid))['summary']
    store.update(sid, summary=summary)
    output = tmp_path / 'summary.docx'
    export_file(output, 'docx', store.get(sid), section='Summary')
    assert output.stat().st_size > 500
    assert 'email the report' in summary

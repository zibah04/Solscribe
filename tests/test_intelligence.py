import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest

from test_live_ui import app, window
from solscribe import reports
from solscribe.intelligence import extract_facts
from solscribe.ollama import Cancelled, OllamaClient


def session(text, speaker='Speaker'):
    return {'title': 'Planning', 'segments': [{'start': 12, 'end': 18, 'speaker': speaker, 'text': text}]}


def test_commitments_keep_explicit_owner_deadline_and_source():
    item = extract_facts(session('I will send the invoice by Friday.', 'Alice'))['action_items'][0]
    assert item['owner'] == 'Alice' and item['deadline'] == 'Friday'
    assert item['source_start'] == 12 and item['verification'] == 'Source commitment'
    assert item['evidence'] == 'I will send the invoice by Friday.'


def test_named_assignment_does_not_use_the_wrong_speaker():
    item = extract_facts(session('Alice will send the report.', 'Bob'))['action_items'][0]
    assert item['owner'] == 'Alice' and item['deadline'] == 'Unspecified'
    item = extract_facts(session('I will ask Bob to review the report.', 'Alice'))['action_items'][0]
    assert item['owner'] == 'Alice'


@pytest.mark.parametrize('text', ['If the tests pass, we will launch.', 'We agreed to launch?', 'Maybe Alice will send it.'])
def test_tentative_words_are_not_confirmed_actions_or_decisions(text):
    facts = extract_facts(session(text))
    assert facts['decisions'] == []
    assert all(not item['explicit'] and item['verification'] == 'Needs review' for item in facts['action_items'])


def test_unknown_owner_is_never_filled_from_attendee_metadata():
    data = session('I will send the report.')
    data['attendees'] = 'Alice, Bob'
    assert extract_facts(data)['action_items'][0]['owner'] == 'Unspecified'


def test_duplicates_at_different_timestamps_are_removed():
    data = session('We agreed to launch next week.')
    data['segments'].append({**data['segments'][0], 'start': 50, 'end': 60})
    assert len(extract_facts(data)['decisions']) == 1
    result = reports.draft_local(data)
    assert result['summary'].count('We agreed to launch next week.') < 4


def test_utf8_chunking_preserves_every_character():
    text = 'Ẹ káàrọ̀ 世界 – résumé\n' * 1000
    chunks = reports._byte_chunks(text, max_bytes=1000)
    assert ''.join(chunks) == text
    assert all(len(part.encode()) <= 1000 for part in chunks)


def test_noncontracting_long_summary_is_rejected_instead_of_silently_truncated(monkeypatch):
    monkeypatch.setattr(reports, '_ask_ollama', lambda *args: 'too much ' * 3000)
    with pytest.raises(ValueError, match='did not reduce'):
        reports.draft_ai(session('This meeting has many points. ' * 2000))


def test_unsupported_dates_and_assignments_are_flagged():
    warnings = reports.audit_report({'minutes': 'Date: 2099-01-01\nOwner: Invented Person'}, session('We discussed a report.'))
    assert any('2099-01-01' in warning for warning in warnings)
    assert any('Invented Person' in warning for warning in warnings)


@pytest.fixture
def server():
    state = {'models': ['test:latest'], 'output': '{"summary":"# Summary","minutes":"# Minutes","memo":"# Memo","actions":"Owner: Invented Person"}',
             'delay': False, 'release': threading.Event(), 'started': threading.Event(), 'calls': []}
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args): pass
        def do_GET(self):
            self.send_response(200); self.end_headers()
            self.wfile.write(json.dumps({'models': [{'name': name} for name in state['models']]}).encode())
        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            state['calls'].append(payload)
            self.send_response(200); self.end_headers()
            if payload.get('keep_alive') == 0:
                self.wfile.write(b'{}')
                return
            state['started'].set()
            if state['delay']:
                state['release'].wait(5)
            try:
                self.wfile.write((json.dumps({'response': state['output'], 'done': True, 'prompt_eval_count': 100}) + '\n').encode())
            except (BrokenPipeError, ConnectionResetError):
                pass
    http = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    http.daemon_threads = True
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    yield state, http.server_port
    state['release'].set()
    http.shutdown(); http.server_close(); thread.join(2)


def test_local_streaming_client_validates_model_and_report(server):
    state, port = server
    client = OllamaClient(port=port)
    with reports.using_client(client):
        result = reports.draft_ai(session('I will send the report.', 'Alice'), 'test')
    client.release()
    assert result['minutes'] == '# Minutes'
    assert result['verification'] == 'Draft'
    assert result['action_items'][0]['owner'] == 'Alice'
    assert 'Invented Person' not in result['actions']
    assert any('Invented Person' in warning for warning in result['warnings'])


def test_missing_local_model_does_not_trigger_a_download(server):
    state, port = server
    state['models'] = []
    with pytest.raises(ValueError, match='not installed'):
        OllamaClient(port=port).generate('test', 'hello')
    assert not state['calls']


def test_cancel_interrupts_a_waiting_local_writing_request(server):
    state, port = server
    state['delay'] = True
    client, errors = OllamaClient(port=port), []
    def run():
        try: client.generate('test', 'hello')
        except Exception as exc: errors.append(exc)
    thread = threading.Thread(target=run)
    thread.start()
    assert state['started'].wait(2)
    began = time.monotonic()
    client.cancel()
    thread.join(2)
    assert not thread.is_alive() and isinstance(errors[0], Cancelled)
    assert time.monotonic() - began < 2


def test_action_register_edits_are_independent_of_written_notes(window):
    window.load_demo()
    data = reports.draft_local(window.store.get(window.session_id))
    window._report_session_id = window.session_id
    window._reports_ready(data)
    before = window.doc_edits['Action items'].toPlainText()
    window.action_table.item(0, 1).setText('Confirmed owner')
    window.persist()
    saved = window.store.get(window.session_id)
    assert saved['action_items'][0]['owner'] == 'Confirmed owner'
    assert saved['action_items'][0]['verification'] == 'Edited by user'
    assert window.doc_edits['Action items'].toPlainText() == before


def test_reviewed_state_is_explicit_and_clears_after_editing(window):
    window.doc_edits['Summary'].setPlainText('Notes to review')
    window.review_checks[0].setChecked(True)
    window.persist()
    assert window.store.get(window.session_id)['reviewed_at']
    window.doc_edits['Summary'].setPlainText('Changed notes')
    window.persist()
    assert not window.store.get(window.session_id)['reviewed_at']

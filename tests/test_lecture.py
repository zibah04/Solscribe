"""Lecture study aids, evidence integrity, migration, practice and export regressions."""
import copy
import json
import sqlite3
from pathlib import Path
import pytest
from solscribe.lecture import (draft_lecture, draft_lecture_ai, source_units, source_hash,
                               validate_items, render_cards)
from solscribe.storage import Store
from solscribe.exporters import export_file, section_content
from test_live_ui import app, window, until


def lesson(*texts):
    return {'title': 'Study · Biology', 'session_type': 'lecture', 'segments': [
        {'start': float(i * 15), 'end': float(i * 15 + 12), 'speaker': 'Lecturer', 'text': text}
        for i, text in enumerate(texts)]}


@pytest.fixture
def lecture():
    return lesson('Osmosis is a movement of water across a partially permeable membrane.',
                  'For example, water can enter a cell in a dilute solution.',
                  'A catalyst means a substance that speeds up a reaction without being consumed.',
                  'It does not change the equilibrium position.')


def test_notes_and_revision_retain_source_words(lecture):
    result = draft_lecture(lecture)
    validate_items(result['study_items'])
    for heading in ('Lecture outline', 'Key concepts', 'Definitions', 'Examples'):
        assert heading in result['study_notes']
    definitions = [i for i in result['study_items'] if i['kind'] == 'definition']
    assert {i['title'] for i in definitions} == {'Osmosis', 'A catalyst'}
    assert len([i for i in result['study_items'] if i['kind'] == 'revision']) == 2
    for item in result['study_items']:
        assert item['evidence'] in ' '.join(s['text'] for s in lecture['segments'])
        assert item['segment_indices']
    assert result == draft_lecture(lecture), 'IDs and ordering must be stable'


def test_fragmented_live_captions_join_into_one_definition():
    session = lesson('Photosynthesis is', 'a process that turns light into chemical energy.', 'For example,', 'plants make sugars.')
    result = draft_lecture(session)
    definition = next(i for i in result['study_items'] if i['kind'] == 'definition')
    assert definition['segment_indices'] == [0, 1]
    assert definition['source_start'] == 0 and definition['source_end'] == 27
    assert 'Photosynthesis is a process' in definition['evidence']
    assert 'For example, plants' in next(i for i in result['study_items'] if i['kind'] == 'example')['text']


def test_late_topics_survive_long_lecture():
    session = lesson(*[f'Topic {i} is a distinct process with condition {i}.' for i in range(250)])
    result = draft_lecture(session)
    for kind in ('outline', 'concept', 'definition', 'revision'):
        assert any('249' in i['evidence'] for i in result['study_items'] if i['kind'] == kind)
    assert len(result['study_items']) <= 104


def test_operators_negation_and_unicode_are_not_deduplicated_or_changed():
    texts = ('Compare a+b with a-b. Do not assume they are equal.', 'ΔG = ΔH − TΔS.', 'x² + y² = r².', 'a+b', 'a-b')
    result = draft_lecture(lesson(*texts))
    evidence = '\n'.join(i['evidence'] for i in result['study_items'])
    for value in ('a+b', 'a-b', 'Do not assume', 'ΔG = ΔH − TΔS', 'x² + y² = r²'):
        assert value in evidence


def test_no_invented_definitions_or_examples():
    result = draft_lecture(lesson('This is a difficult question.', 'We should review the graph carefully.'))
    assert not any(i['kind'] in ('definition', 'example') for i in result['study_items'])
    assert 'No explicit definitions identified' in result['study_notes']
    assert all(i['answer'] == i['evidence'] for i in result['study_items'] if i['kind'] == 'revision')


def test_long_unpunctuated_and_single_word_passages_are_retained():
    text = 'word ' * 1300 + 'final_concept'
    units = source_units(lesson(text)['segments'])
    assert ' '.join(u['text'] for u in units) == text.strip()
    units = source_units(lesson('z' * 2200)['segments'])
    assert ''.join(u['text'] for u in units) == 'z' * 2200


def test_hash_tracks_words_and_timing_but_not_speaker(lecture):
    changed = copy.deepcopy(lecture['segments'])
    changed[0]['speaker'] = 'Professor'
    assert source_hash(changed) == source_hash(lecture['segments'])
    changed[0]['text'] += ' Correction.'
    assert source_hash(changed) != source_hash(lecture['segments'])


def test_empty_transcript_is_rejected():
    with pytest.raises(ValueError, match='transcript'):
        draft_lecture(lesson())


def test_ai_uses_quoted_answers_and_preserves_all_source_chunks(monkeypatch):
    requests = []
    def ask(model, prompt, response_json):
        rows = json.loads(prompt.split('DATA:\n', 1)[1]); requests.extend(rows)
        return json.dumps({'items': [{'kind': 'revision', 'source_id': rows[-1]['source_id'], 'text': 'Explain this concept.'}]})
    monkeypatch.setattr('solscribe.reports._ask_ollama', ask)
    session = lesson(*[f'Concept {i} is a process. ' + 'Detail ' * 65 for i in range(35)])
    result = draft_lecture_ai(session, 'test')
    assert len(requests) == len(source_units(session['segments']))
    assert requests[-1]['source_id'] == len(requests) - 1
    assert all(i['answer'] == i['evidence'] for i in result['study_items'] if i['kind'] == 'revision')
    assert any('AI concepts' in w for w in result['warnings'])


@pytest.mark.parametrize('record', [
    {'kind': 'revision', 'source_id': 999, 'text': 'Why?'},
    {'kind': 'revision', 'source_id': True, 'text': 'Why?'},
    {'kind': 'concept', 'source_id': 0, 'text': 'Water moves at 9000 metres per second.'},
    {'kind': 'example', 'source_id': 0, 'text': 'An invented example'},
])
def test_ai_rejects_bad_sources_numbers_and_categories(lecture, monkeypatch, record):
    monkeypatch.setattr('solscribe.reports._ask_ollama', lambda *args: json.dumps({'items': [record]}))
    with pytest.raises(ValueError):
        draft_lecture_ai(lecture, 'test')


def test_worker_falls_back_to_quick_lecture_notes(lecture, monkeypatch):
    from solscribe import ui
    monkeypatch.setattr(ui, 'draft_lecture_ai', lambda *args: (_ for _ in ()).throw(ConnectionError('unavailable')))
    worker = ui.ReportWorker(lecture, 'ai', 'missing-model')
    output = []
    worker.done.connect(output.append)
    worker.run()
    assert output[0]['fallback'] and output[0]['study_items']
    assert 'summary' not in output[0]


def test_schema_four_migration_preserves_meeting_documents(tmp_path):
    store = Store(tmp_path)
    sid = store.create('Existing meeting')
    store.update(sid, summary='Keep summary', minutes='Keep minutes')
    with store.connect() as conn:
        for field in ('session_type', 'study_notes', 'study_items', 'study_source_hash', 'study_warnings'):
            conn.execute('ALTER TABLE sessions DROP COLUMN ' + field)
        conn.execute('PRAGMA user_version=4')
    migrated = Store(tmp_path)
    saved = migrated.get(sid)
    assert saved['session_type'] == 'meeting' and saved['study_items'] == []
    assert saved['summary'] == 'Keep summary' and saved['minutes'] == 'Keep minutes'
    with sqlite3.connect(migrated.database) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 5
    assert list(migrated.backups.glob('auto-*.db'))


def test_future_schema_is_not_downgraded(tmp_path):
    store = Store(tmp_path)
    with store.connect() as conn: conn.execute('PRAGMA user_version=6')
    with pytest.raises(sqlite3.DatabaseError, match='newer version'):
        Store(tmp_path)
    with sqlite3.connect(store.database) as conn:
        assert conn.execute('PRAGMA user_version').fetchone()[0] == 6


def create_ui_notes(window):
    window.mode_combo.setCurrentIndex(window.mode_combo.findData('lecture'))
    window.load_demo()
    window.generate_reports()
    until(lambda: not window._report_active)
    return window.store.get(window.session_id)


def test_meeting_lecture_switch_keeps_both_sets_of_notes(window, app):
    window.load_demo()
    window.doc_edits['Summary'].setPlainText('A meeting summary to keep.')
    sid = window.session_id
    window.mode_combo.setCurrentIndex(1)
    window.study_edit.setPlainText('Study notes to keep.')
    assert window.persist()
    assert window.tabs.isTabVisible(7) and not window.tabs.isTabVisible(1)
    window.mode_combo.setCurrentIndex(0)
    assert window.tabs.isTabVisible(1) and not window.tabs.isTabVisible(7)
    window.load_session(sid)
    assert window.doc_edits['Summary'].toPlainText() == 'A meeting summary to keep.'
    assert window.study_edit.toPlainText() == 'Study notes to keep.'


def test_failed_save_restores_mode_without_discarding_edits(window, monkeypatch):
    original = window.store.update
    window.doc_edits['Summary'].setPlainText('Unsaved edit')
    monkeypatch.setattr(window.store, 'update', lambda *a, **k: (_ for _ in ()).throw(OSError('full')))
    window.mode_combo.setCurrentIndex(1)
    assert window.session_type() == 'meeting' and window.tabs.isTabVisible(1)
    assert window.doc_edits['Summary'].toPlainText() == 'Unsaved edit'
    monkeypatch.setattr(window.store, 'update', original)
    assert window.persist()


def test_revision_reveal_edits_reload_and_source_jump(window, app):
    session = create_ui_notes(window)
    assert session['study_items'] and session['session_type'] == 'lecture'
    assert window.tabs.currentIndex() == 7
    window.study_tabs.setCurrentIndex(1)
    assert not window.revision_answer.isVisible()
    window.reveal_answer.click()
    assert window.revision_answer.isVisible()
    original = copy.deepcopy(window.study_items[window._revision_indices[0]])
    window.revision_answer.setPlainText('My edited answer')
    window.revision_question.setPlainText('My edited question?')
    assert window.persist()
    window.load_session(session['id'])
    item = window.study_items[window._revision_indices[0]]
    assert item['answer'] == 'My edited answer' and item['question'] == 'My edited question?'
    assert item['evidence'] == original['evidence']
    window._revision_source()
    assert window.study_quote.toPlainText().endswith(original['evidence'])
    window._study_jump()
    assert window.tabs.currentIndex() == 0


def test_transcript_changes_warn_without_erasing_study_notes(window):
    session = create_ui_notes(window)
    before = window.study_edit.toPlainText()
    window.table.item(0, 2).setText('A corrected transcript sentence.')
    assert window.persist()
    assert 'transcript has changed' in window.study_notice.text()
    assert window.study_edit.toPlainText() == before
    assert window.current_session['study_items'] == session['study_items']


def test_new_and_imported_recordings_inherit_lecture_mode(window, tmp_path):
    window.mode_combo.setCurrentIndex(1)
    sid = window.new_session()
    assert window.store.get(sid)['session_type'] == 'lecture'
    path = tmp_path / 'Lecture.wav'; path.write_bytes(b'audio')
    window.import_audio(path)
    assert window.current_session['session_type'] == 'lecture'


def test_guide_can_choose_lecture_and_practice(window):
    window.show_quick_guide()
    guide = window._guide
    guide.purpose.setCurrentIndex(1); guide.practice.setChecked(True)
    guide.accept()
    assert window.session_type() == 'lecture'
    assert 'Sample' in window.current_session['title'] and window.table.rowCount()


@pytest.mark.parametrize('fmt', ['txt', 'md', 'docx', 'pdf', 'json', 'srt'])
def test_lecture_exports_roundtrip_evidence_and_unicode(tmp_path, fmt):
    session = lesson('ΔG means the change in free energy. Compare a+b with a-b.', 'For example, x² + y² = r².')
    output = draft_lecture(session)
    session.update(output)
    session['study_items'][-1]['answer'] = 'Edited answer: ΔG = ΔH − TΔS.'
    path = export_file(tmp_path / ('lecture.' + fmt), fmt, session, 'Transcript' if fmt == 'srt' else 'Revision cards')
    assert path.is_file() and path.stat().st_size > 30
    if fmt == 'json':
        saved = json.loads(path.read_text())
        assert saved['study_items'][-1]['answer'] == session['study_items'][-1]['answer']
    elif fmt in ('txt', 'md'):
        assert 'ΔG = ΔH − TΔS' in path.read_text(encoding='utf-8')
    elif fmt == 'docx':
        from docx import Document
        assert 'ΔG = ΔH − TΔS' in '\n'.join(p.text for p in Document(path).paragraphs)
    elif fmt == 'pdf':
        from pypdf import PdfReader
        assert 'ΔG' in '\n'.join(page.extract_text() for page in PdfReader(path).pages)


def test_untrusted_markup_is_literal_in_study_notes():
    from solscribe.document_markup import plain_text
    result = draft_lecture(lesson('For example, <img src="x"> and **bold** are source characters.'))
    text = plain_text(result['study_notes'])
    assert '<img src="x">' in text and '**bold**' in text


@pytest.mark.parametrize('size', [(1092, 570), (683, 340)])
@pytest.mark.parametrize('theme', ['light', 'dark'])
def test_lecture_mode_at_laptop_sizes(window, app, size, theme):
    create_ui_notes(window)
    window.set_theme(theme); window.resize(*size); app.processEvents()
    assert window.mode_combo.isVisible()
    window.work_scroll.ensureWidgetVisible(window.mode_combo)
    app.processEvents()
    assert window.rect().contains(window.mode_combo.mapTo(window, window.mode_combo.rect().center()))
    window.work_scroll.ensureWidgetVisible(window.study_tabs)
    assert window.study_edit.viewport().height() >= 100
    assert window.credit_label.isVisible()

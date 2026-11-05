import re
from docx import Document
from pypdf import PdfReader
import pytest
from solscribe.exporters import export_file, _strip_md


SOURCE = '''# Meeting notes

## Résumé · Ẹ káàrọ̀ · Ελληνικά · Привет

The formula is 2 * 3 = 6. Keep value_name and A_B exactly.
Use **important words**, *emphasis* and `literal_code`.

1. First step
2. Second step

| Task | Owner | Due |
| --- | --- | --- |
| Email the report | Alice | Friday |

Read [the guide](https://example.com/help).
Literal <nothtml> remains text.
'''


def test_plain_text_preserves_operators_underscores_links_and_tables():
    text = _strip_md(SOURCE)
    for value in ('2 * 3 = 6', 'value_name', 'A_B', 'literal_code', '1. First step', '2. Second step',
                  'Email the report | Alice | Friday', 'https://example.com/help', '<nothtml>'):
        assert value in text
    assert '**important words**' not in text


def test_word_preserves_tables_unicode_and_page_fields(tmp_path):
    path = export_file(tmp_path / 'notes.docx', 'docx', {'minutes': SOURCE})
    doc = Document(path)
    paragraphs = '\n'.join(p.text for p in doc.paragraphs)
    assert '2 * 3 = 6' in paragraphs and 'Ελληνικά' in paragraphs and 'Ẹ káàrọ̀' in paragraphs
    assert doc.tables[0].cell(1, 0).text == 'Email the report'
    assert any(run.bold for paragraph in doc.paragraphs for run in paragraph.runs if 'important' in run.text)
    assert 'PAGE' in doc.sections[0].footer._element.xml


def test_pdf_preserves_unicode_and_long_content_across_pages(tmp_path):
    content = SOURCE + '\n\n' + '\n\n'.join('Paragraph %d. ' % i + 'Important conversation details. ' * 30 for i in range(35))
    path = export_file(tmp_path / 'résumé.pdf', 'pdf', {'minutes': content})
    pdf = PdfReader(path)
    text = '\n'.join(page.extract_text() for page in pdf.pages)
    assert len(pdf.pages) > 2
    assert '2 * 3 = 6' in text and 'value_name' in text and 'Привет' in text
    assert 'Paragraph 34.' in text and 'Email the report' in text
    assert all('Prepared with SolScribe' in page.extract_text() for page in pdf.pages)


def test_pdf_can_split_a_table_row_longer_than_one_page(tmp_path):
    content = '# Action register\n\n| Task | Owner |\n|---|---|\n| ' + 'Long task details ' * 1000 + 'FINAL_WORD | Unspecified |'
    path = export_file(tmp_path / 'long-table.pdf', 'pdf', {'actions': content}, 'Action items')
    pdf = PdfReader(path)
    assert len(pdf.pages) > 1
    assert 'FINAL_WORD' in '\n'.join(page.extract_text() for page in pdf.pages)


@pytest.mark.parametrize('format', ['docx', 'pdf', 'md', 'txt', 'json'])
def test_invalid_destination_does_not_remove_existing_files(tmp_path, format):
    existing = tmp_path / 'keep.txt'
    existing.write_text('Keep this')
    with pytest.raises(OSError):
        export_file(tmp_path / 'does-not-exist' / ('file.' + format), format, {'minutes': SOURCE})
    assert existing.read_text() == 'Keep this'

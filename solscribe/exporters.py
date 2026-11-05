"""Export native documents, portable text, JSON and subtitle files."""
from __future__ import annotations

import html
import json
import re
import os
import tempfile
from datetime import datetime
from pathlib import Path

from .reports import transcript_text
from .document_markup import blocks, inline_runs, plain_text


def safe_filename(name):
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', (name or 'Meeting')).strip(' .-')
    if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', safe.split('.')[0], re.I):
        safe = 'Meeting - ' + safe
    return safe[:85].rstrip(' .') or 'Meeting'


def srt_timestamp(seconds):
    millis = max(0, round(float(seconds or 0) * 1000))
    h, r = divmod(millis, 3600000)
    m, r = divmod(r, 60000)
    s, ms = divmod(r, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def srt_text(segments):
    lines = []
    index = 1
    for s in segments:
        if not (s.get('text') or '').strip():
            continue
        start = srt_timestamp(s.get('start'))
        end = srt_timestamp(max(float(s.get('end') or 0), float(s.get('start') or 0) + .25))
        lines.extend([str(index), f'{start} --> {end}', s['text'].strip(), ''])
        index += 1
    return '\n'.join(lines)


def section_content(session, section):
    if section == 'Action register':
        from .intelligence import render_actions
        from .reports import stamp
        return render_actions(session.get('action_items', []), session.get('title') or 'Meeting', stamp)
    if section == 'Transcript':
        title = session.get('title') or 'Meeting'
        text = transcript_text(session.get('segments') or [])
        return f'# Transcript · {title}\n\n{text or "(No transcript yet.)"}'
    mapping = {'Summary': 'summary', 'Minutes': 'minutes', 'Memo': 'memo', 'Action items': 'actions'}
    content = (session.get(mapping.get(section, ''), '') or '').strip()
    result = content or f'# {section}\n\nNo content yet. Generate or write this document first.'
    return result if session.get('reviewed_at') else '*Draft · review names, decisions and dates before sharing.*\n\n' + result


def _strip_md(text):
    return plain_text(text)


def write_docx(path, content):
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    document = Document()
    section = document.sections[0]
    section.top_margin = Inches(.78)
    section.bottom_margin = Inches(.7)
    section.left_margin = Inches(.9)
    section.right_margin = Inches(.9)
    normal = document.styles['Normal']
    normal.font.name = 'Aptos'
    normal.font.size = Pt(10.5)
    normal.font.color.rgb = RGBColor(45, 55, 72)
    for style in ('Title', 'Heading 1', 'Heading 2'):
        document.styles[style].font.name = 'Aptos Display'
        document.styles[style].font.color.rgb = RGBColor(42, 48, 91)
    def runs(paragraph, children):
        for text, bold, italic, code in inline_runs(children):
            run = paragraph.add_run(text)
            run.bold, run.italic = bold, italic
            if code:
                run.font.name = 'Consolas'
    for block in blocks(content):
        kind = block['kind']
        if kind == 'table':
            rows = block['rows']
            table = document.add_table(rows=0, cols=max(len(row) for row in rows))
            table.style = 'Light Shading Accent 1'
            for row in rows:
                cells = table.add_row().cells
                for index, children in enumerate(row):
                    runs(cells[index].paragraphs[0], children)
        elif kind == 'code':
            document.add_paragraph(block['text']).style = 'No Spacing'
        else:
            if kind == 'heading':
                paragraph = document.add_heading(level=min(3, block['level'] - 1))
            else:
                paragraph = document.add_paragraph(style='List Bullet' if block['prefix'] == '- ' else 'Quote' if kind == 'quote' else None)
            if block['prefix'] and block['prefix'] != '- ':
                paragraph.add_run(block['prefix'])
            runs(paragraph, block['children'])
    footer = section.footer.paragraphs[0]
    footer.text = f'SolScribe  |  Prepared {datetime.now().strftime("%d %b %Y")}'
    footer.style = 'Caption'
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    footer.add_run('  |  Page ')
    field = OxmlElement('w:fldSimple')
    field.set(qn('w:instr'), 'PAGE')
    footer._p.append(field)
    document.save(str(path))


def write_pdf(path, content):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, XPreformatted

    font = 'Helvetica'
    bold_font = 'Helvetica-Bold'
    # A Unicode typeface is essential for international transcripts.
    from pathlib import Path as P
    candidates = [
        P('C:/Windows/Fonts/segoeui.ttf'),
        P('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
        P('/usr/local/share/fonts/DejaVuSans.ttf'),
    ]
    for file in candidates:
        if file.is_file():
            try:
                pdfmetrics.registerFont(TTFont('SolScribeFont', str(file)))
                font = 'SolScribeFont'
                bold_font = font
                break
            except Exception:
                pass
    styles = getSampleStyleSheet()
    ink = colors.HexColor('#212944')
    purple = colors.HexColor('#6C62C8')
    body = ParagraphStyle('SolBody', parent=styles['Normal'], fontName=font,
                          fontSize=9.8, leading=15.8, textColor=ink, alignment=TA_LEFT,
                          spaceAfter=7)
    title_style = ParagraphStyle('SolTitle', parent=body, fontName=bold_font, fontSize=19,
                                 leading=25, textColor=purple, spaceAfter=14)
    heading_style = ParagraphStyle('SolHeading', parent=body, fontName=bold_font, fontSize=12,
                                   leading=17, textColor=purple, spaceBefore=12, spaceAfter=7,
                                   keepWithNext=True)
    bullet_style = ParagraphStyle('SolBullet', parent=body, leftIndent=15, firstLineIndent=-9)
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=2.1*cm, rightMargin=2.1*cm,
                            topMargin=2.1*cm, bottomMargin=2.0*cm,
                            title='SolScribe document', author='SolScribe')
    story = []
    def markup(children):
        values = []
        for text, bold, italic, code in inline_runs(children):
            value = html.escape(text).replace('\n', '<br/>')
            if bold: value = '<b>' + value + '</b>'
            if italic: value = '<i>' + value + '</i>'
            values.append(value)
        return ''.join(values)
    for block in blocks(content):
        kind = block['kind']
        if kind == 'table':
            rows = [[Paragraph(markup(cell), body) for cell in row] for row in block['rows']]
            columns = max(map(len, rows))
            for row in rows:
                row.extend([Paragraph('', body)] * (columns - len(row)))
            table = LongTable(rows, colWidths=[doc.width / columns] * columns, repeatRows=1,
                              splitByRow=1, splitInRow=1)
            table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#EEECFA')),
                                       ('GRID', (0,0), (-1,-1), .35, colors.HexColor('#D9DCEC')),
                                       ('VALIGN', (0,0), (-1,-1), 'TOP'),
                                       ('LEFTPADDING', (0,0), (-1,-1), 6),
                                       ('RIGHTPADDING', (0,0), (-1,-1), 6)]))
            story.extend([table, Spacer(1, 9)])
        elif kind == 'code':
            story.append(XPreformatted(html.escape(block['text']), body))
        else:
            style = title_style if kind == 'heading' and block['level'] == 1 else heading_style if kind == 'heading' else bullet_style if block['prefix'] else body
            story.append(Paragraph(html.escape(block['prefix']) + markup(block['children']), style))

    def decorate(canvas, pdf_doc):
        canvas.saveState()
        width, _ = A4
        canvas.setStrokeColor(colors.HexColor('#DEDDF5'))
        canvas.line(2.1*cm, 1.55*cm, width - 2.1*cm, 1.55*cm)
        canvas.setFont(font, 8)
        canvas.setFillColor(colors.HexColor('#777C96'))
        canvas.drawString(2.1*cm, 1.2*cm, 'Prepared with SolScribe')
        canvas.drawRightString(width - 2.1*cm, 1.2*cm, str(pdf_doc.page))
        canvas.restoreState()

    doc.build(story, onFirstPage=decorate, onLaterPages=decorate)


def _write_export(path, fmt, session, section='Minutes'):
    """Returns the written output path. fmt: docx, pdf, txt, md, json, srt."""
    path = Path(path)
    fmt = fmt.lower().lstrip('.')
    if fmt == 'json':
        content = json.dumps(session, indent=2, ensure_ascii=False)
        path.write_text(content, encoding='utf-8')
    elif fmt == 'srt':
        if section != 'Transcript':
            raise ValueError('SRT subtitles require the Transcript section.')
        path.write_text(srt_text(session.get('segments') or []), encoding='utf-8-sig')
    else:
        content = section_content(session, section)
        if fmt == 'docx':
            write_docx(path, content)
        elif fmt == 'pdf':
            write_pdf(path, content)
        elif fmt in ('txt', 'md'):
            path.write_text(content if fmt == 'md' else _strip_md(content), encoding='utf-8-sig')
        else:
            raise ValueError(f'Unsupported export format: {fmt}')
    return path


def export_file(path, fmt, session, section='Minutes'):
    """Publish only a complete export; a failure leaves any existing file intact."""
    destination = Path(path)
    handle, temporary = tempfile.mkstemp(prefix='.solscribe-', suffix=destination.suffix,
                                         dir=destination.parent)
    os.close(handle)
    try:
        _write_export(temporary, fmt, session, section)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)
    return destination

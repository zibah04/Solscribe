"""Export native documents, portable text, JSON and subtitle files."""
from __future__ import annotations

import html
import json
import re
from datetime import datetime
from pathlib import Path

from .reports import transcript_text


def safe_filename(name):
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', (name or 'Meeting')).strip(' .-')
    return safe[:85] or 'Meeting'


def srt_timestamp(seconds):
    millis = max(0, round(float(seconds or 0) * 1000))
    h, r = divmod(millis, 3600000)
    m, r = divmod(r, 60000)
    s, ms = divmod(r, 1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'


def srt_text(segments):
    lines = []
    for index, s in enumerate(segments, start=1):
        if not (s.get('text') or '').strip():
            continue
        start = srt_timestamp(s.get('start'))
        end = srt_timestamp(max(float(s.get('end') or 0), float(s.get('start') or 0) + .25))
        lines.extend([str(index), f'{start} --> {end}', s['text'].strip(), ''])
    return '\n'.join(lines)


def section_content(session, section):
    if section == 'Transcript':
        title = session.get('title') or 'Meeting'
        text = transcript_text(session.get('segments') or [])
        return f'# Transcript · {title}\n\n{text or "(No transcript yet.)"}'
    mapping = {'Summary': 'summary', 'Minutes': 'minutes', 'Memo': 'memo', 'Action items': 'actions'}
    content = (session.get(mapping.get(section, ''), '') or '').strip()
    return content or f'# {section}\n\nNo content yet. Generate or write this document first.'


def _content_lines(markdown):
    """Parse common document syntax without treating arbitrary meeting text as HTML."""
    for line in markdown.splitlines():
        value = line.rstrip()
        if not value:
            yield 'blank', ''
        elif value.startswith('# '):
            yield 'title', value[2:].strip()
        elif value.startswith('## '):
            yield 'section', value[3:].strip()
        elif value.startswith('### '):
            yield 'subsection', value[4:].strip()
        elif value.startswith('- '):
            yield 'bullet', value[2:].strip()
        else:
            yield 'body', value.replace('  ', ' ').strip()


def _strip_md(text):
    return re.sub(r'\*\*(.*?)\*\*', r'\1', text).replace('*', '')


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
    for kind, value in _content_lines(content):
        if kind == 'blank':
            continue
        if kind == 'title':
            document.add_heading(_strip_md(value), 0)
        elif kind == 'section':
            document.add_heading(_strip_md(value), 1)
        elif kind == 'subsection':
            document.add_heading(_strip_md(value), 2)
        elif kind == 'bullet':
            document.add_paragraph(_strip_md(value), style='List Bullet')
        else:
            # Metadata lines use bold label if provided in Markdown.
            p = document.add_paragraph()
            parts = re.split(r'(\*\*[^*]+\*\*)', value)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    p.add_run(part[2:-2]).bold = True
                elif part:
                    p.add_run(part)
    footer = section.footer.paragraphs[0]
    footer.text = f'SolScribe  |  Prepared {datetime.now().strftime("%d %b %Y")}'
    footer.style = 'Caption'
    document.save(str(path))


def write_pdf(path, content):
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether

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
    for kind, raw in _content_lines(content):
        if kind == 'blank':
            story.append(Spacer(1, 5))
            continue
        value = html.escape(raw)
        value = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', value)
        if kind == 'title':
            story.append(Paragraph(value, title_style))
        elif kind in ('section', 'subsection'):
            story.append(Paragraph(value, heading_style))
        elif kind == 'bullet':
            story.append(Paragraph('• ' + value, bullet_style))
        else:
            story.append(Paragraph(value, body))

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


def export_file(path, fmt, session, section='Minutes'):
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

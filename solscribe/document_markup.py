"""CommonMark blocks shared by DOCX/PDF/TXT exporters; literal text is preserved."""
from markdown_it import MarkdownIt


def blocks(markdown: str):
    tokens = MarkdownIt('commonmark', {'html': False}).enable('table').parse(markdown)
    result, lists, heading, quote, table, row, cell = [], [], 0, False, None, None, None
    for token in tokens:
        kind = token.type
        if kind == 'heading_open': heading = int(token.tag[1:])
        elif kind == 'heading_close': heading = 0
        elif kind == 'blockquote_open': quote = True
        elif kind == 'blockquote_close': quote = False
        elif kind in ('bullet_list_open', 'ordered_list_open'):
            lists.append(None if kind == 'bullet_list_open' else int(token.attrGet('start') or 1))
        elif kind in ('bullet_list_close', 'ordered_list_close'):
            lists.pop()
        elif kind == 'table_open': table = []
        elif kind == 'tr_open': row = []
        elif kind in ('th_open', 'td_open'): cell = []
        elif kind in ('th_close', 'td_close'):
            row.append(cell)
        elif kind == 'tr_close': table.append(row)
        elif kind == 'table_close':
            result.append({'kind': 'table', 'rows': table})
            table = None
        elif kind == 'inline':
            children = token.children or []
            if table is not None:
                cell.extend(children)
            else:
                prefix = ''
                if lists:
                    prefix = '- ' if lists[-1] is None else f'{lists[-1]}. '
                    if lists[-1] is not None: lists[-1] += 1
                result.append({'kind': 'heading' if heading else ('quote' if quote else 'paragraph'),
                               'level': heading, 'children': children, 'prefix': prefix})
        elif kind in ('fence', 'code_block'):
            result.append({'kind': 'code', 'text': token.content.rstrip('\n')})
        elif kind == 'hr': result.append({'kind': 'code', 'text': '—' * 12})
    return result


def inline_runs(tokens):
    bold, italic, link = False, False, None
    for token in tokens:
        if token.type == 'strong_open': bold = True
        elif token.type == 'strong_close': bold = False
        elif token.type == 'em_open': italic = True
        elif token.type == 'em_close': italic = False
        elif token.type == 'link_open': link = token.attrGet('href')
        elif token.type == 'link_close':
            if link: yield f' ({link})', bold, italic, False
            link = None
        elif token.type == 'image':
            yield f'[Image: {token.content}] ({token.attrGet("src") or ""})', bold, italic, False
        elif token.type in ('softbreak', 'hardbreak'):
            yield '\n', bold, italic, False
        elif token.type in ('text', 'code_inline'):
            yield token.content, bold, italic, token.type == 'code_inline'


def plain_text(markdown: str) -> str:
    output = []
    for block in blocks(markdown):
        if block['kind'] == 'table':
            for row in block['rows']:
                output.append(' | '.join(''.join(run[0] for run in inline_runs(cell)) for cell in row))
        elif block['kind'] == 'code': output.append(block['text'])
        else: output.append(block['prefix'] + ''.join(run[0] for run in inline_runs(block['children'])))
        output.append('')
    return '\n'.join(output).rstrip()

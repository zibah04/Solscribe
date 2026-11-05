"""Lightweight source-grounded decisions and editable action items."""
from __future__ import annotations
from collections import defaultdict
import re
import uuid

UNSPECIFIED = 'Unspecified'
_CONDITIONAL = re.compile(r"\b(if|unless|maybe|might|could|should|propose|suggest|not|never|didn't|don't|won't)\b", re.I)
_DECISION = re.compile(r'\b(we (?:agreed|decided|approved)|it was (?:agreed|decided)|(?:decision|proposal) (?:was|is) approved|resolved to)\b', re.I)
_COMMIT = re.compile(r"\b((?i:i will|i['’]ll|we will|we['’]ll)|[A-Z][\w'-]+(?: [A-Z][\w'-]+){0,2} (?:will|agreed to|is responsible for))\b")
_POSSIBLE = re.compile(r'\b(needs? to|must|please|should|will|assigned|follow up)\b', re.I)
_DEADLINE = re.compile(r'\b(?:by|before|on)\s+((?:(?:next|this)\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)|tomorrow|today|next week|\d{4}-\d{2}-\d{2}|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b', re.I)


def normalized(text: str) -> str:
    return re.sub(r'\W+', ' ', text.casefold()).strip()


def extract_facts(session: dict) -> dict:
    decisions, proposals, actions, seen = [], [], [], set()
    for segment in session.get('segments', []):
        text = (segment.get('text') or '').strip()
        if not text:
            continue
        # Timestamp is evidence, not part of the duplicate identity.
        identity = normalized(text)
        if identity in seen:
            continue
        seen.add(identity)
        ambiguous = bool(_CONDITIONAL.search(text)) or '?' in text
        if _DECISION.search(text):
            (proposals if ambiguous else decisions).append(dict(segment))
        explicit = _COMMIT.search(text)
        if not explicit and not _POSSIBLE.search(text):
            continue
        owner = UNSPECIFIED
        if explicit:
            subject = explicit.group(0)
            if re.match(r"^i(?: will|['’]ll)", subject, re.I):
                label = segment.get('speaker') or 'Speaker'
                if label.casefold() not in ('speaker', 'unknown', 'written notes'):
                    owner = label
            elif not re.match(r"^we(?: will|['’]ll)", subject, re.I):
                owner = re.split(r' (?:will|agreed to|is responsible for)', subject)[0]
        due = _DEADLINE.search(text)
        deadline = due.group(1) if due else UNSPECIFIED
        is_explicit = bool(explicit) and not ambiguous
        verification = 'Needs review' if not is_explicit else ('Confirm owner' if owner == UNSPECIFIED else 'Source commitment')
        actions.append({'id': uuid.uuid5(uuid.NAMESPACE_URL, f'{segment.get("start",0)}:{identity}').hex,
                        'task': text, 'owner': owner, 'deadline': deadline, 'status': 'Open',
                        'source_start': float(segment.get('start') or 0),
                        'source_end': float(segment.get('end') or 0), 'evidence': text,
                        'verification': verification, 'explicit': is_explicit})
    return {'decisions': decisions, 'proposals': proposals, 'action_items': actions}


def grouped_highlights(segments: list[dict]) -> dict[str, list[dict]]:
    groups, seen = defaultdict(list), set()
    categories = [('Money and budgets', r'\b(budget|cost|invoice|payment|spend)\w*\b'),
                  ('Testing and quality', r'\b(test|bug|quality|risk|review)\w*\b'),
                  ('Plans and delivery', r'\b(launch|release|deadline|deliver|schedule|plan)\w*\b')]
    for segment in segments:
        text = (segment.get('text') or '').strip()
        identity = normalized(text)
        if not identity or identity in seen:
            continue
        seen.add(identity)
        category = next((name for name, pattern in categories if re.search(pattern, text, re.I)), 'Other discussion')
        groups[category].append(segment)
    return dict(groups)


def render_actions(items: list[dict], title: str, stamp) -> str:
    lines = [f'# Action items · {title}', '', '*Draft · check the task, owner and deadline against the cited words.*', '']
    if not items:
        return '\n'.join(lines + ['No clear action items were found. Add any agreed tasks after reviewing the conversation.'])
    for item in items:
        lines += [f'## {item["task"]}', f'**Owner:** {item["owner"]}  ',
                  f'**Due:** {item["deadline"]}  ', f'**Status:** {item["status"]}  ',
                  f'**Review:** {item["verification"]}  ',
                  f'**Source [{stamp(item["source_start"]) if item.get("source_start") is not None else "Not linked"}]:** {item.get("evidence") or "Manually entered"}', '']
    return '\n'.join(lines)

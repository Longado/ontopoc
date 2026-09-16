"""A few business questions the user fixes up front, so a later run can be judged on the same questions instead of on
whatever the model asks that time. The query is the one a person already saw and agreed with; code runs it again and
says whether the answer moved, or stops and names the break when the ontology no longer carries the fields it needs."""
from __future__ import annotations

from datetime import datetime, timezone

from ontology_poc_generator.ontology_questions import run_query

MAX_ACCEPTANCE = 3   # ponytail: a short list a consultant can agree with a client; the model's own round still asks more
MAX_NOTE = 200


class AcceptanceError(ValueError):
    """The acceptance questions cannot be saved; the message is shown to the user."""


def parse_acceptance(items) -> list[dict]:
    if not isinstance(items, list) or not items:
        raise AcceptanceError('至少要保存一道验收问题')
    if len(items) > MAX_ACCEPTANCE:
        raise AcceptanceError(f'验收问题最多 {MAX_ACCEPTANCE} 道')
    out = []
    for i, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            raise AcceptanceError(f'第 {i} 道验收问题格式不对')
        question = str(item.get('question') or '').strip()
        if not 0 < len(question) <= 300:
            raise AcceptanceError(f'第 {i} 道的问题要写 1–300 个字')
        if not isinstance(item.get('query'), dict):
            raise AcceptanceError(f'第 {i} 道没有查询：只有人看过、认可口径的问题才能存为验收问题')
        note = str(item.get('note') or '').strip()
        if len(note) > MAX_NOTE:
            raise AcceptanceError(f'第 {i} 道的口径说明最多 {MAX_NOTE} 个字')
        out.append({'question': question, 'query': item['query'], 'note': note,
                    'answer': item.get('answer'), 'status': item.get('status'), 'path': item.get('path')})
    return out


def check_acceptance(ontology: dict, bundle: dict, items: list[dict]) -> dict:
    """Run every saved query on this run's ontology and data; keep the previous answer beside the new one."""
    checked = []
    for item in items:
        previous = {k: item.get(k) for k in ('status', 'answer', 'path')} if item.get('status') else None
        result = run_query(ontology, bundle, item['query'])
        if result['status'] == 'ontology_gap':
            # the query a person agreed with no longer fits this ontology: stop here instead of guessing a new meaning
            result = {'status': 'broken', 'reason': result['reason']}
        checked.append({'question': item['question'], 'note': item['note'], 'query': item['query'], **result,
                        'previous': previous,
                        'changed': None if previous is None else (result.get('answer') != previous['answer'] or result['status'] != previous['status'])})
    return {'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'items': checked,
            'answered': sum(i['status'] == 'answered' for i in checked), 'total': len(checked)}

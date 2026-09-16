"""A few business questions the user fixes up front, so a later run can be judged on the same questions instead of on
whatever the model asks that time. The query is the one a person already saw and agreed with; code runs it again and
says whether the answer moved, or stops and names the break when the ontology no longer carries the fields it needs."""
from __future__ import annotations

from datetime import datetime, timezone

from ontology_poc_generator.ontology_compare import match_types
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
        out.append({'question': question, 'query': item['query'], 'note': note, 'snapshot': item.get('snapshot'),
                    'answer': item.get('answer'), 'status': item.get('status'), 'path': item.get('path')})
    return out


def _used(query: dict) -> tuple[set, list]:
    """The relation keys a query walks, and the type key it starts from."""
    keys = list(query.get('via') or [])
    for d in query.get('group_by') or []:
        keys += list((d or {}).get('via') or []) if isinstance(d, dict) else []
    return {query.get('start')}, list(dict.fromkeys(keys))


def snapshot_of(ontology: dict, query: dict) -> dict:
    """What the query points at, as it looks now: enough to recognise the same things after the model renames them."""
    relations = {r['key']: r for r in ontology['relations']}
    used_relations = [relations[k] for k in _used(query)[1] if k in relations]
    wanted = {query.get('start'), *(end for r in used_relations for end in (r['from'], r['to']))}
    return {'types': [{k: t.get(k) for k in ('key', 'label', 'populated_from')} for t in ontology['object_types'] if t['key'] in wanted],
            'relations': [{k: r.get(k) for k in ('key', 'from', 'to', 'label', 'source')} for r in used_relations]}


def remap_query(query: dict, snapshot: dict, ontology: dict) -> tuple[dict | None, str]:
    """The saved query, rewritten for this run's names. Matching is by what things are built from, never by guessing:
    an object must read the same table by the same identity fields (or carry the same name), and a relation must join
    the matched ends with no other candidate beside it."""
    label = {t['key']: (t.get('label') or t['key']) for t in snapshot['types']}
    mapping = match_types(snapshot['types'], ontology['object_types'])
    missing = [label[k] for k in {query.get('start'), *(e for r in snapshot['relations'] for e in (r['from'], r['to']))} if k and k not in mapping]
    if missing:
        return None, f'这一版本体里找不到{"、".join(sorted(missing))}，这道题要重新确认'
    relation_map = {}
    for r in snapshot['relations']:
        ends = {mapping[r['from']], mapping[r['to']]}
        candidates = [o for o in ontology['relations'] if {o['from'], o['to']} == ends]
        if not candidates:
            return None, f'这一版本体里 {label[r["from"]]} 和 {label[r["to"]]} 之间没有关系了，这道题要重新确认'
        if len(candidates) > 1:
            same_source = [o for o in candidates if o.get('source') == r.get('source')]
            candidates = same_source if len(same_source) == 1 else candidates
        if len(candidates) > 1:
            return None, f'{label[r["from"]]} 和 {label[r["to"]]} 之间这一版有 {len(candidates)} 条关系，分不清原来用的是哪一条，请人确认'
        relation_map[r['key']] = candidates[0]['key']
    walk = lambda via: [relation_map.get(k, k) for k in via or []]
    return {**query, 'start': mapping[query['start']], 'via': walk(query.get('via')),
            **({'group_by': [{**d, 'via': walk(d.get('via'))} if isinstance(d, dict) else d for d in query['group_by']]} if query.get('group_by') else {})}, ''


def check_acceptance(ontology: dict, bundle: dict, items: list[dict]) -> dict:
    """Run every saved query on this run's ontology and data; keep the previous answer beside the new one."""
    checked = []
    for item in items:
        previous = {k: item.get(k) for k in ('status', 'answer', 'path')} if item.get('status') else None
        query, problem = remap_query(item['query'], item['snapshot'], ontology) if item.get('snapshot') else (item['query'], '')
        result = {'status': 'broken', 'reason': problem} if problem else run_query(ontology, bundle, query)
        if result['status'] == 'ontology_gap':
            # the query a person agreed with no longer fits this ontology: stop here instead of guessing a new meaning
            result = {'status': 'broken', 'reason': result['reason']}
        checked.append({'question': item['question'], 'note': item['note'], 'query': query if not problem else item['query'],
                        'snapshot': snapshot_of(ontology, query) if not problem else item.get('snapshot'), **result,
                        'previous': previous,
                        'changed': None if previous is None else (result.get('answer') != previous['answer'] or result['status'] != previous['status'])})
    return {'checked_at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'items': checked,
            'answered': sum(i['status'] == 'answered' for i in checked), 'total': len(checked)}

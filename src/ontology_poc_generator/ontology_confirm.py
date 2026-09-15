"""A person's item-by-item judgement of a built ontology, turned into a reference ontology for that file.
Kept objects carry the tables and identity fields they were built from, so later runs are matched by what they read,
not by what they are called; renamed objects keep that match. The reference is what evaluation 3 compares against."""
from __future__ import annotations

VERDICTS = ('ok', 'wrong')
MAX_LABEL = 40
MAX_ADDED = 30


class ConfirmError(ValueError):
    """The decisions do not fit the ontology; the message is shown to the user."""


def _label(value, what: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > MAX_LABEL:
        raise ConfirmError(f'{what}的名字要写 1–{MAX_LABEL} 个字')
    return value.strip()


def _verdicts(given, known: dict, what: str) -> dict:
    if not isinstance(given, dict):
        raise ConfirmError(f'{what}的判断格式不对')
    out = {}
    for key, d in given.items():
        if key not in known:
            raise ConfirmError(f'本体里没有这个{what}：{key}')
        if not isinstance(d, dict) or d.get('verdict') not in VERDICTS:
            raise ConfirmError(f'{what} {key} 的 verdict 只能是 ok 或 wrong')
        out[key] = d
    return out


def confirmed_reference(ontology: dict, decisions: dict) -> dict:
    types = {t['key']: t for t in ontology['object_types']}
    relations = {r['key']: r for r in ontology['relations']}
    if not isinstance(decisions, dict):
        raise ConfirmError('判断格式不对')
    type_d = _verdicts(decisions.get('types') or {}, types, '对象')
    rel_d = _verdicts(decisions.get('relations') or {}, relations, '关系')
    added = decisions.get('added') or []
    if not isinstance(added, list) or len(added) > MAX_ADDED:
        raise ConfirmError(f'补充的对象最多 {MAX_ADDED} 个')
    kept = []
    for key, d in type_d.items():
        if d['verdict'] == 'ok':
            t = types[key]
            kept.append({'key': key, 'label': _label(d.get('label'), '对象') or t.get('label') or key,
                         'populated_from': [{'source': p.get('source'), 'identity': p.get('identity') or {}} for p in t.get('populated_from') or []]})
    kept_keys = {t['key'] for t in kept}
    links = []
    for key, d in rel_d.items():
        if d['verdict'] != 'ok':
            continue
        r = relations[key]
        dropped = [types[end].get('label') or end for end in (r['from'], r['to']) if end not in kept_keys]
        if dropped:
            raise ConfirmError(f'关系 {key} 判了"对"，但它连着的{"、".join(dropped)}没有判"对"')
        links.append({'key': key, 'from': r['from'], 'to': r['to']})
    names = {t['label'] for t in kept}
    for i, name in enumerate(added):
        name = _label(name, f'补充的第 {i + 1} 个对象')
        if name in names:
            raise ConfirmError(f'补充的对象“{name}”和已有的对象重名')
        names.add(name)
        kept.append({'key': f'added_{i + 1}', 'label': name, 'populated_from': []})
    if not kept:
        raise ConfirmError('至少要判一个对象"对"，或补充一个对象')
    return {'object_types': kept, 'relations': links}

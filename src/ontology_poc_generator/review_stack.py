"""The review stack: what a person can say to each thing in 要确认的事, and what a "not applicable" or "known exception"
keeps beside it so that it can come back.

Every kind of item declares its reply menu (at most four replies, in the order the keys 1 to 4 pick them): the kind's own
choices (repeat rule options, "same or different"), and of the four general replies the ones that mean something for it:
  confirm         the thing is as the item says (words are needed for a kind that is only answered in words)
  wrong           it is not; the words say what is right
  not_applicable  it does not apply here (the model read a column as a code, a table nobody needs)
  exception       it is true and known, left as it is for a reason that is written down

A reply is kept with who gave it and whether it was decided one by one ('single') or with others in one action ('bulk').
"Not applicable" and "exception" are decisions that stay decided: they keep an anchor, what the item was about when it was
decided (the values of a code column with their rows, the keys that repeated, the rows not linked). The same item on the
next upload is not asked again unless an anchor breaks: something new is in it, or a count has moved by the same measure as
for confirmed definitions (anchors.moved). Then it is asked again, with what changed beside the old decision.

The clean band is what can be approved together in one action, after the list is shown: code columns whose every suggestion the data
backs, and relations whose check found every row connected. Anything with a failed check or a weak suggestion is never in it; the service
works the band out again when asked to approve, and refuses an id that is not in it. A bulk approval is recorded as 'bulk'."""
from __future__ import annotations

from ontology_poc_generator.anchors import moved

REPLY_SAYS = {'confirm': '确认', 'wrong': '不对', 'not_applicable': '不适用', 'exception': '已知例外'}
RECORDED = ('not_applicable', 'exception')   # decisions that stay decided and carry an anchor
MODES = ('single', 'bulk')
EXAMPLE_ROWS = 3
EXAMPLE_COLUMNS = 6
NEW_SHOWN = 3

OWN_SAYS = {'expected': '本来就没有对应', 'incomplete': '数据没导全', 'distinct': '是不同的对象', 'same': '是同一个', 'rename': '名字说错了，改名',
            'name_right': '名字是对的', 'keep_both': '每一行都留', 'keep_latest': '只留最新的一行', 'data_error': '当作数据错误'}
YES_NO = ('found_elsewhere', 'unstable')   # "is it?" / "keep it?": yes is confirm, no is wrong
TEXT_ONLY = ('check_finding', 'data_gap', 'data_gaps', 'unanswered', 'name_source', 'name_by_view', 'name_values')
OWN = {'unlinked': ('expected', 'incomplete'), 'same_name': ('distinct', 'same'), 'merged': ('distinct', 'same'),
       'name_vs_calc': ('rename', 'name_right')}
# a kind with its own endpoint is answered there: its confirmation needs the labels or the rule, "not a code" is a different
# endpoint with its own effect on every place a code is shown. The card endpoint takes only what has no other way in.
BY_ENDPOINT = {'code_meaning': ('exception',), 'repeated_key': ('exception',)}


def menu(kind: str) -> list[dict]:
    """The replies of a kind in key order: [{'id', 'label', 'needs_text'}]. Empty for a kind that is settled by doing something
    (removing a condition, judging each object, filling the card)."""
    if kind in OWN:
        ids = [*OWN[kind], 'not_applicable', 'exception']
    elif kind in YES_NO:
        ids = ['confirm', 'wrong', 'not_applicable', 'exception']
    elif kind in TEXT_ONLY:
        ids = ['confirm', 'not_applicable', 'exception']
    elif kind == 'code_meaning':
        ids = ['confirm', 'not_applicable', 'exception']
    elif kind == 'repeated_key':
        ids = ['keep_both', 'keep_latest', 'data_error', 'exception']
    else:
        return []
    says = {**OWN_SAYS, **REPLY_SAYS, **({'confirm': '记下答复'} if kind in TEXT_ONLY else {'confirm': '确认含义'} if kind == 'code_meaning' else {}),
            **({'not_applicable': '不是代码'} if kind == 'code_meaning' else {})}
    return [{'id': i, 'label': says[i], 'needs_text': i in ('wrong', 'exception') or (i == 'confirm' and kind in TEXT_ONLY)} for i in ids]


def check_mode(payload: dict) -> str:
    """How a request says it was decided: 'single' when it does not say. Raises ValueError with the text the person reads."""
    mode = payload.get('mode', 'single')
    if mode not in MODES:
        raise ValueError('mode 只能是 single 或 bulk')
    return mode


def card_replies(kind: str) -> tuple:
    """The general replies the card endpoint takes for this kind."""
    if kind in BY_ENDPOINT:
        return BY_ENDPOINT[kind]
    return tuple(m['id'] for m in menu(kind) if m['id'] in REPLY_SAYS)


def anchor_of(item: dict) -> dict:
    """What the item is about, as a decision about it keeps it: {'noun', 'members' (what it names: values, keys, lines of facts),
    'counts' ({what counted: how many}) and 'total' (of how many rows)}. An item that did not work its own out is about its facts."""
    return item.get('anchor') or {'noun': '内容', 'members': list(item.get('facts') or [])}


def anchor_changes(was: dict, now: dict) -> list[str]:
    """What is no longer as it was when the decision was made (empty: it holds): something new among the members, or a count that
    became a different share of the rows (anchors.moved)."""
    changes = []
    new = [m for m in now.get('members', []) if m not in set(was.get('members', []))]
    if new:
        changes.append(f'多了{now.get("noun", "内容")}：{"、".join(new[:NEW_SHOWN])}{"等" if len(new) > NEW_SHOWN else ""}')
    for name, count in (was.get('counts') or {}).items():
        k, n = (now.get('counts') or {}).get(name, 0), now.get('total', 0)
        if moved(count, was.get('total', 0), k, n):
            changes.append(f'{name}：上次 {count} 行（共 {was["total"]} 行），现在 {k} 行（共 {n} 行）')
    return changes


def example_rows(table: str, records: list[dict], rows: list[int], first: list[str]) -> dict:
    """At most EXAMPLE_ROWS of the table's rows, as the person reads them: the columns in `first` come first, then the table's
    own order, EXAMPLE_COLUMNS in all; empty cells show as blank."""
    columns = list(dict.fromkeys([*first, *(k for r in records for k in r)]))[:EXAMPLE_COLUMNS]
    return {'table': table, 'columns': columns, 'rows': [['' if records[i].get(c) is None else str(records[i].get(c)) for c in columns] for i in rows[:EXAMPLE_ROWS]]}


def code_examples(item: dict, bundle: dict) -> dict | None:
    """One row for each of the first values of a code column, from the table as it was stored."""
    source, column = item['column']['source'], item['column']['column']
    records = (bundle['sources'].get(source) or {}).get('records') or []
    rows = []
    for v in item['column']['values']:
        hit = next((i for i, r in enumerate(records) if str(r.get(column)) == v['value']), None)
        if hit is not None:
            rows.append(hit)
    return example_rows(source, records, rows, [column]) if rows else None


def code_check(values: list[dict]) -> dict | None:
    """What the data says to the model's suggestions for a code column's values: backed or not. Without a suggestion there is nothing checked."""
    guessed = [v for v in values if v.get('recommendation')]
    if not guessed:
        return None
    weak = [v for v in guessed if not v['recommendation']['strong']]
    return {'status': 'weak' if weak else 'passed',
            'text': (f'模型建议了 {len(guessed)} 个含义，其中 {len(weak)} 个数据没有支持' if weak else f'模型建议了 {len(guessed)} 个含义，数据都有支持')}


# the clean band: what can be approved together, after the list is shown

def code_band(items: list[dict]) -> list[dict]:
    """The code columns whose every unconfirmed value has the model's suggestion and the data behind it (a pattern in another column,
    enough rows: `recommendation.strong`) and nothing waiting for a second look. One value with no suggestion, or a suggestion the data
    does not back, keeps the whole column out: it is a person's. Each: {'id', 'kind', 'title', 'lines', 'posted'} where `posted` is
    what approving confirms, value by value."""
    band = []
    for item in items:
        if item['kind'] != 'code_meaning' or item.get('reopened'):
            continue
        todo = [v for v in item['column']['values'] if not v['confirmed']]
        if todo and all(v['preselected'] and v['recommendation'].get('label') and not v['waiting'] for v in todo):
            column = item['column']
            band.append({'id': item['id'], 'kind': 'code_meaning', 'title': f'「{column["source"]}」的「{column["column"]}」',
                         'lines': [f'{v["value"]} = {v["recommendation"]["label"]}：{v["recommendation"].get("basis") or "数据有支持"}' for v in todo],
                         'posted': [{'value': v['value'], 'label': v['recommendation']['label'], 'description': v['recommendation'].get('description') or ''} for v in todo]})
    return band


def relation_band(relations: list[dict], decisions: dict | None, label, relation_name) -> list[dict]:
    """The relations nobody has judged whose check found every row connected on every side, no object reached through more than one, and
    no declared cardinality broken, and whose two objects a person has already judged right (a relation counts only with both).
    relations: the run's data_checks.relations; label gives an object's name and relation_name a relation's."""
    types, judged = ((decisions or {}).get('types') or {}), ((decisions or {}).get('relations') or {})
    band = []
    for r in relations:
        if (judged.get(r['key']) or {}).get('verdict') or not r['sides'] or r['cardinality'].get('holds') is False:
            continue
        if any((types.get(end) or {}).get('verdict') != 'ok' for end in (r['from'], r['to'])):
            continue
        if any(s['matched'] != s['rows'] or s['fanout']['keys'] for s in r['sides']):
            continue
        band.append({'id': f'relation:{r["key"]}', 'kind': 'relation', 'title': relation_name(r),
                     'lines': [f'{s["rows"]} / {s["rows"]} 行{label(s["other"])}都找得到{label(s["object"])}，「{s["lookup"]}」表里没有重复的编号' for s in r['sides']]})
    return band

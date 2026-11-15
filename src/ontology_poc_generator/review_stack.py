"""The review stack: what a person can say to each thing in 要确认的事, and what a "not applicable" or "known exception"
keeps beside it so that it can come back.

Every kind of item declares its reply menu (at most four replies, in the order the keys 1 to 4 pick them): the kind's own
choices (repeat rule options, "same or different"), and of the four general replies the ones that mean something for it:
  confirm         the thing is as the item says (words are needed for a kind that is only answered in words)
  wrong           it is not; the words say what is right
  not_applicable  it does not apply here (the model read a column as a code, a table nobody needs)
  exception       it is true and known, left as it is for a reason that is written down

A reply is kept with who gave it and how it was decided: one by one ('single'). Only the bulk approval endpoint records 'bulk'; no other request can say it.
"Not applicable" and "exception" are decisions that stay decided: they keep an anchor, what the item was about when it was
decided (the values of a code column with their rows, the keys that repeated, the rows not linked). The same item on the
next upload is not asked again unless an anchor breaks: something new is in it, or a count has moved by the same measure as
for confirmed definitions (anchors.moved). Then it is asked again, with what changed beside the old decision.

The clean band is what can be approved together in one action, after the list is shown: only what code verifies completely (a relation
whose every row connects, with no fan-out and a cardinality that holds). What the data cannot say, a code's meaning above all, is one by one.
The service works the band out again inside the write and refuses what is not in it. A bulk approval is recorded as 'bulk', for the
approved items only."""
from __future__ import annotations

from ontology_poc_generator.anchors import moved

REPLY_SAYS = {'confirm': '确认', 'wrong': '不对', 'not_applicable': '不适用', 'exception': '已知例外'}
RECORDED = ('not_applicable', 'exception')   # decisions that stay decided and carry an anchor
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
    """How a request says it was decided: always 'single' here ('bulk' is the bulk approval's alone, which works it out itself). Raises ValueError
    with the text the person reads when a request says anything else."""
    mode = payload.get('mode', 'single')
    if mode != 'single':
        raise ValueError('mode 只能是 single；批量通过只能走“一起通过”')
    return mode


def card_replies(kind: str) -> tuple:
    """The general replies the card endpoint takes for this kind."""
    if kind in BY_ENDPOINT:
        return BY_ENDPOINT[kind]
    return tuple(m['id'] for m in menu(kind) if m['id'] in REPLY_SAYS)


def anchor_of(item: dict) -> dict | None:
    """What the item is about, as a decision about it keeps it: {'noun', 'members' (what it names: values, keys),
    'counts' ({what counted: how many}), 'total' (of how many rows; absent when a count has nothing to be measured against) and 'unit'
    (what is counted, rows when absent)}. None for an item that has nothing structured: its facts are
    sentences with counts in them, capped at three, and they change when another card's decision does, so they are no anchor
    and a decision about such an item never comes back by itself."""
    return item.get('anchor')


def anchor_changes(was: dict, now: dict) -> list[str]:
    """What is no longer as it was when the decision was made (empty: it holds): something new among the members, or a count that
    became a different share of the rows (anchors.moved)."""
    changes = []
    new = [m for m in now.get('members', []) if m not in set(was.get('members', []))]
    if new:
        changes.append(f'多了{now.get("noun", "内容")}：{"、".join(new[:NEW_SHOWN])}{"等" if len(new) > NEW_SHOWN else ""}')
    unit = now.get('unit', '行')
    for name, count in (was.get('counts') or {}).items():
        k, n = (now.get('counts') or {}).get(name, 0), now.get('total')
        if was.get('total') is None or n is None:   # nothing to measure it against: the count itself, grown to more than twice or fallen below half
            if moved(count, 1, k, 1):
                changes.append(f'{name}：上次 {count} {unit}，现在 {k} {unit}')
        elif moved(count, was['total'], k, n):
            changes.append(f'{name}：上次 {count} {unit}（共 {was["total"]} {unit}），现在 {k} {unit}（共 {n} {unit}）')
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

CARDINALITY_SAYS = {'one_to_one': '一对一', 'many_to_one': '多对一', 'one_to_many': '一对多'}


def cardinality_line(cardinality: dict, source: str, target: str) -> str | None:
    """Why the relation's cardinality is no reason to look at it, in words; None when it is. Either it was declared one-to-one or
    many-to-one and the data holds to it (a declared many-to-many holds to anything, and a one-to-many multiplies the rows of what
    it is walked from: neither says "safe"), or it was not declared and the data is computed one-to-one or many-to-one: one `source`
    reaches at most one `target`, so walking the relation never multiplies rows."""
    declared, observed = cardinality.get('declared'), cardinality.get('observed')
    if declared:
        return f'声明为{CARDINALITY_SAYS[declared]}，数据里成立' if declared in ('one_to_one', 'many_to_one') and cardinality.get('holds') is True else None
    return f'没有声明，按数据算是{CARDINALITY_SAYS[observed]}：每个{source}只对一个{target}' if observed in ('one_to_one', 'many_to_one') else None


def relation_band(relations: list[dict], decisions: dict | None, label, relation_name) -> list[dict]:
    """The relations nobody has judged that code can fully verify: every row of a table with rows connects on every end (an end is
    checked as a side, or is the relation's own table read by its own key), no object is reached through more than one, and the
    cardinality is declared and holds or computed without fan-out (cardinality_line says which). Their two objects are already judged
    right by a person: a relation counts only with both. This is all that a person has no judgement to add to: a code's meaning, which
    the data cannot say, is never here. relations: the run's data_checks.relations; label gives an object's name and relation_name
    a relation's."""
    types, judged = ((decisions or {}).get('types') or {}), ((decisions or {}).get('relations') or {})
    band = []
    for r in relations:
        if (judged.get(r['key']) or {}).get('verdict') or any((types.get(end) or {}).get('verdict') != 'ok' for end in (r['from'], r['to'])):
            continue
        sides = r['sides']
        if not sides or {s['end'] for s in sides} | set(r.get('own_ends') or []) != {'from', 'to'}:
            continue   # an end that nothing was looked up against is not verified
        if any((r.get('own_blank') or {}).get(end) != 0 for end in r.get('own_ends') or []):
            continue   # rows that name no object at their own end: "every row connects" would count them as rows of that object
        if any(not s['rows'] or s['matched'] != s['rows'] or s['fanout']['keys'] for s in sides):
            continue
        how = cardinality_line(r['cardinality'], label(r['from']), label(r['to']))
        if how is None:
            continue
        band.append({'id': f'relation:{r["key"]}', 'kind': 'relation', 'title': relation_name(r),
                     'lines': [*(f'{s["rows"]} / {s["rows"]} 行{label(s["other"])}都找得到{label(s["object"])}，「{s["lookup"]}」表里没有重复的编号' for s in sides), how]})
    return band

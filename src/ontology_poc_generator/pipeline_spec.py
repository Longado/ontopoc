"""The pipeline requirements (编排需求单): what the data check, the open items, the data-meaning card, the derived measures
and the adopted rules already say about how the data has to be prepared, gathered for whoever builds the data pipeline
(a canvas, Data Factory, dbt). OntoPoc does not change the data and does not write a pipeline: it says what is to be done
and why. Every entry is put together by code from records that exist, with no model call, and says where it comes from:
found in the data (code), answered by the client (who, from where, when), or confirmed by a person.
"""
from __future__ import annotations

from datetime import date
import json
import re

from ontology_poc_generator.derived_measures import formula_text
from ontology_poc_generator.handover_form import source_profile
from ontology_poc_generator.ontology_card import NOT_BUSINESS_TIME, _blank, is_padded_number
from ontology_poc_generator.ontology_confirm import without_wrong
from ontology_poc_generator.ontology_eval import _relations, _row_owners
from ontology_poc_generator.open_items import CHOICES, _num, open_items, split_answers
from ontology_poc_generator.public_ontology import _alias_map, _path_exists, bound_instances, normalize_proposal, resolve

ISO = 'YYYY-MM-DD'
# the ways a date is written that a pipeline is asked to put right, besides ISO itself: name, pattern, the groups holding year, month, day
DATE_STYLES = (
    (ISO, re.compile(r'(\d{4})-(\d{2})-(\d{2})'), (1, 2, 3)),
    ('YYYY/M/D', re.compile(r'(\d{4})/(\d{1,2})/(\d{1,2})'), (1, 2, 3)),
    ('YYYY.M.D', re.compile(r'(\d{4})\.(\d{1,2})\.(\d{1,2})'), (1, 2, 3)),
    ('M/D/YYYY', re.compile(r'(\d{1,2})/(\d{1,2})/(\d{4})'), (3, 1, 2)),
    ('YYYY年M月D日', re.compile(r'(\d{4})年(\d{1,2})月(\d{1,2})日'), (1, 2, 3)),
)
MAPPING_LINES = 3   # confirmed spellings and aliases named in one entry
FILES = ('编排需求单.md', '编排需求单.json')

# what a client said of rows that did not link, by choice
REPLIES = {'expected': '客户答复本来就没有对应：用左关联，保留没对上的行', 'incomplete': '客户答复数据没导全：先补数据再关联'}

quote = lambda column: f'「{column}」'


def _entry(kind: str, text: str, source: str, refs=(), **who) -> dict:
    return {'kind': kind, 'text': text, 'source': source, **who, 'refs': list(refs)}


def _code(kind: str, text: str, refs=()) -> dict:
    return _entry(kind, text, 'code', refs)


def _client(kind: str, text: str, answers: list, refs=()) -> dict:
    """An entry resting on answers: everyone who gave one, the sources they named, and the latest date."""
    return _entry(kind, text, 'client', refs, by='、'.join(dict.fromkeys(a['by'] for a in answers)),
                  basis='；'.join(dict.fromkeys(a['basis'] for a in answers if a.get('basis'))), at=max(a['at'] for a in answers))


def _person(kind: str, text: str, by: str | None, at: str | None, refs=()) -> dict:
    """What a person confirmed, naming them and the day only where the file keeps it."""
    return _entry(kind, text, 'person', refs, **({'by': by} if by else {}), **({'at': at} if at else {}))


def _answered(answer):
    return None if _blank(answer) else answer


def _style(text: str) -> str | None:
    for name, pattern, (y, m, d) in DATE_STYLES:
        found = pattern.fullmatch(text)
        if found:
            try:
                date(int(found[y]), int(found[m]), int(found[d]))
            except ValueError:
                return None
            return name
    return None


def _date_styles(values: list) -> dict:
    """Style -> the first example, when every value is a date written in one of the known ways; {} otherwise."""
    styles = {}
    for v in values:
        name = _style(v)
        if name is None:
            return {}
        styles.setdefault(name, v)
    return styles


def _text_values(records: list, path: str) -> list:
    out = []
    for r in records:
        for v in resolve(r, path):
            if v is not None and str(v).strip():
                out.append(str(v).strip())
    return out


def _title_rows(profile: dict) -> list:
    rows = profile['skipped_rows']
    if not rows:
        return []
    shown = '；'.join(rows[:2]) + ('等' if len(rows) > 2 else '')
    return [_code('title_rows', f'接入时跳过表头上方 {_num(len(rows))} 行标题（{shown}）')]


def _grain(t: dict) -> list:
    grain = t['grain']
    answer, unique = _answered(grain['answer']), grain['unique']
    facts = (f'识别字段 {"、".join(unique["fields"])} 共 {_num(unique["distinct"])} 种组合，{_num(unique["duplicates"])} 组重复，'
             f'{_num(unique["blank"])} 行的识别字段为空') if unique else '这张表没有对象的识别字段，查不了重复'
    text = f'一行是什么：{answer["says"] if answer else "还没说清"}；{facts}'
    return [_client('grain', text, [answer], [grain['id']]) if answer else _code('grain', text, [grain['id']])]


def _dedupe(t: dict) -> list:
    unique = t['grain']['unique']
    if not unique or not unique['duplicates']:
        return []
    return [_code('dedupe', f'有 {_num(unique["duplicates"])} 组识别值重复（例：{"、".join(unique["examples"])}），编排时要定保留哪一行', [t['grain']['id']])]


def _amounts(t: dict) -> list:
    """What the card says about the figure columns, in the order a pipeline meets them: the ones that are not added up
    row by row, the ones that are, the codes, then the clean-up the figures need."""
    business = [d for d in t['dates'] if (d['answer'] or {}).get('value') == 'business']
    dates = '、'.join(quote(d['field']) for d in business)
    date_ids = [d['id'] for d in business]
    mine = lambda *values: [a for a in t['amounts'] if (a['answer'] or {}).get('value') in values]
    out = []
    one_row_each = (t['grain']['answer'] or {}).get('value') == 'one_object'
    for a in mine('running', 'latest'):
        if one_row_each and a['answer']['value'] == 'latest':   # each row is already its object's latest value
            out.append(_client('latest', f'{quote(a["field"])}是{a["answer"]["says"]}：这张表一行一个对象，可以按对象直接相加；'
                                         '不要再和明细表里同一对象的数重复相加', [a['answer']], [a['id']]))
            continue
        sort = f'排序用业务日期列{dates}' if business else '排序列待定'
        out.append(_client('latest', f'{quote(a["field"])}是{a["answer"]["says"]}：汇总前先按它所属的对象保留最新一行再加总，不能跨行相加。{sort}；按哪个对象保留，编排时定',
                           [a['answer']], [a['id'], *date_ids]))
    for a in mine('period_to_date'):
        fixed = f'业务日期列{dates}' if business else '业务日期列（卡上还没标出）'
        out.append(_client('period', f'{quote(a["field"])}是{a["answer"]["says"]}：先按{fixed}固定一期再汇总，跨期不能相加', [a['answer']], [a['id'], *date_ids]))
    flows = mine('flow')
    if flows:
        out.append(_client('sum_ok', f'{"、".join(quote(a["field"]) for a in flows)}可以直接汇总：每行是这一笔自己的数，可以跨行相加',
                           [a['answer'] for a in flows], [a['id'] for a in flows]))
    for a in mine('not_amount'):
        out.append(_client('not_amount', f'{quote(a["field"])}按编码处理，转成文本，不参与汇总', [a['answer']], [a['id']]))
    for a in t['amounts']:
        noise = a.get('noise')
        if not noise or (a['answer'] or {}).get('value') == 'not_amount':   # a column the client called a code is kept as text, not made into numbers
            continue
        held = ''.join(f"'{k}' {_num(n)} 个、" for k, n in noise['placeholders'].items()).rstrip('、')
        parts = [*([f'去掉千分位（{_num(noise["thousands"])} 个值）'] if noise['thousands'] else []), *([f'占位符 {held}转成空'] if held else [])]
        out.append(_code('number_clean', f'{quote(a["field"])}要转成数值：{"；".join(parts)}', [a['id']]))
    return out


def _text_columns(profile: dict, records: list) -> list:
    """Id columns whose leading zeros a number type would drop, and date columns not written the ISO way. Only a column
    of text can be either, and both are read off its values."""
    ids, dates = [], []
    for f in profile['fields']:
        if f['type'] != 'VARCHAR':
            continue
        values = _text_values(records, f['path'])
        padded = list(dict.fromkeys(v for v in values if is_padded_number(v)))
        if padded:
            ids.append(_code('keep_text_id', f'{quote(f["path"])}按文本保留，转成数字会丢掉前导 0（例：{"、".join(padded[:2])}）'))
        styles = _date_styles(values)
        if styles and set(styles) != {ISO}:
            seen = '；'.join(f'{name}，例 {example}' for name, example in styles.items())
            dates.append(_code('date_format', f'{quote(f["path"])}统一成 {ISO}（看到的写法：{seen}）'))
    return [*ids, *dates]


def _date_meaning(t: dict) -> list:
    out = []
    for d in t['dates']:
        answer, declared = _answered(d['answer']), _answered(d['declared'])
        if not (answer or declared):
            continue
        text = (f'{quote(d["field"])}是{answer["says"]}' if answer else f'{quote(d["field"])}是什么时间还没说清') \
            + (f'；{declared["says"]}' if declared else '') \
            + ('。取数时间和录入时间不能当业务期次用' if answer and answer['value'] in NOT_BUSINESS_TIME else '')
        out.append(_client('date_meaning', text, [a for a in (answer, declared) if a], [d['id'], *([d['range_id']] if declared else [])]))
    return out


def _code_mapping(source: str, labels: dict, fit: dict, run: dict) -> list:
    """Spellings and ids the data check found for the objects read from this table (code), and what a person confirmed:
    the same thing written several ways, a value alias of the ontology. An alias is a person's only once the ontology has
    been confirmed."""
    spellings = [x for x in fit.get('identity_spellings') or [] if x['type'] in labels]
    twins = [x for x in fit.get('suspected_duplicates') or [] if x['type'] in labels]
    confirmation = run.get('confirmation')
    variants = [f'{labels[g["type"]]}：{" / ".join(g["values"])}' for g in ((confirmation or {}).get('reference') or {}).get('name_variants') or []
                if g['type'] in labels]
    aliases = [f'{labels[a["type"]]}的值别名：{a["source"]} 表的“{a["value"]}”对应 {a["target_source"]} 表的“{a["target_value"]}”'
               for a in run['ontology'].get('value_aliases') or [] if a['source'] == source and a['type'] in labels]
    found = [*([f'{_num(len(spellings))} 个对象的编号写法不止一种（例：{" / ".join(f"“{v}”" for v in spellings[0]["variants"])}）'] if spellings else []),
             *([f'{_num(len(twins))} 组编号只差前导 0（例：{" / ".join(twins[0]["identities"])}）'] if twins else []),
             *([] if confirmation else aliases)]
    confirmed = [*variants, *(aliases if confirmation else [])]
    refs = [f'check_finding:{key}' for key, hit in (('identity_spellings', spellings), ('suspected_duplicates', twins)) if hit]
    out = [_code('code_mapping', f'建编码对照：{"；".join(found)}。同一个对象要对到同一个编码上', refs)] if found else []
    if confirmed:
        shown = '；'.join(confirmed[:MAPPING_LINES]) + ('等' if len(confirmed) > MAPPING_LINES else '')
        out.append(_person('code_mapping', f'建编码对照，这些已有人确认是同一个：{shown}', confirmation.get('confirmed_by'), confirmation.get('confirmed_at')))
    return out


def _complete(source: str, objects: list) -> list:
    out = []
    for o in objects:
        answer = _answered(o['answer'])
        if answer is None or o['id'].partition(':')[2].partition('|')[0] != source:
            continue
        tail = '，要补数据' + (f'：{answer["note"]}' if answer.get('note') else '') if answer['value'] == 'partial' else '，已确认是全量'
        out.append(_client('complete', f'{o["label"]}：{answer["says"]}{tail}', [answer], [o['id']]))
    return out


def _table(t: dict, profile: dict, records: list, kept: dict, objects: list, fit: dict, run: dict) -> dict:
    labels = {o['type']: kept[o['type']].get('label') or o['type'] for o in t['objects'] if o['type'] in kept}
    return {'source': t['source'], 'rows': t['rows'], 'objects': list(labels.values()),
            'items': [*_title_rows(profile), *_grain(t), *_dedupe(t), *_amounts(t), *_text_columns(profile, records), *_date_meaning(t),
                      *_code_mapping(t['source'], labels, fit, run), *_complete(t['source'], objects)]}


def _columns(pop: dict) -> list:
    return [pop['identity'][k] for k in sorted(pop['identity'])]


def _named_by(r: dict, end: str, types: dict) -> list:
    """The column lists that name one end of a relation in the relation's own table: its binding, else the identity
    columns of each population of that object read from the table."""
    binding = r.get(f'{end}_identity')
    if isinstance(binding, dict):
        return [[binding[k] for k in sorted(binding)]]
    return [_columns(p) for p in types[r[end]]['populated_from'] if p['source'] == r['source']]


def _reference(table: str, columns: list) -> str:
    return f'{table}.{"+".join(columns)}'


def _named_objects(r: dict, end: str, index: int, record: dict, graph: dict, aliases: dict) -> list:
    """The objects one end of a relation names in one row, whether or not they exist and whatever the other end names."""
    if isinstance(r.get(f'{end}_identity'), dict):
        return [inst for _, inst in bound_instances(r, end, record, aliases)]
    return graph['per_record'].get((r['source'], index), {}).get(r[end], [])


def _join(r: dict, ends: tuple, types: dict, bundle: dict, graph: dict, aliases: dict, stat: dict) -> tuple[str, int, str]:
    """One relation as a join: the columns and the counts of the data check (`stat`, its relation entry, so they are the
    open item's), how many rows do not link, and, joined on the columns, the rows of each object that is also read from
    other tables that name one those tables do not have — some of them may be rows the data check links, because the
    object is read from this table too."""
    src = r['source']
    records = bundle['sources'][src]['records']
    said, tables, misses = [], [], []
    for key in dict.fromkeys(r[end] for end in ends):
        mine = [end for end in ends if r[end] == key]
        defined = list({p['source']: (p['source'], _columns(p)) for p in types[key]['populated_from'] if p['source'] != src}.values())
        if not defined:
            continue
        there = [t for t, _ in defined]
        columns = dict.fromkeys(_reference(src, cols) for end in mine for cols in _named_by(r, end, types))
        said.append(f'{" 或 ".join(columns)} 对 {" 或 ".join(_reference(*d) for d in defined)}')
        tables += there
        missed = sum(any(not graph['sources_of'].get(inst, set()).intersection(there)
                         for end in mine for inst in _named_objects(r, end, index, record, graph, aliases))
                     for index, record in enumerate(records))
        if missed:
            misses.append(f'{_num(missed)} 行的{types[key].get("label") or key}在 {"、".join(there)} 里找不到')
    if not said:
        columns = dict.fromkeys(_reference(src, cols) for end in ends for cols in _named_by(r, end, types))
        said = [f'{" 和 ".join(columns)}（对象读自同一张表，不用另外关联）']
    linked, left, empty = stat['linked_rows'], stat['rows'] - stat['linked_rows'], stat.get('empty_rows')
    counts = '，'.join(f'{name} {_num(len(bundle["sources"][name]["records"]))} 行' for name in dict.fromkeys((src, *tables)))
    facts = f'连上 {_num(linked)} 行'
    if left:
        facts += f'；{_num(left)} 行连不上' + (f'（其中 {_num(empty)} 行用来连的编号是空的）' if empty else '')
    elif not misses:
        facts += '，每一行都连上了'
    return f'{"，".join(said)}：{counts}，{facts}', left, (f'按这几列直接关联，{"，".join(misses)}' if misses else '')


def _joins(reviewed: dict, bundle: dict, graph: dict, aliases: dict, stats: dict, answers: dict, listed: set) -> list:
    types = {t['key']: t for t in reviewed['object_types']}
    owners = _row_owners(reviewed, graph)
    out = []
    for r in reviewed['relations']:
        # the object the table is about is not joined to anything: the other end is. A table about neither end, or about
        # both alike, joins both.
        about = [k for k in (r['from'], r['to']) if k in owners.get(r['source'], ())]
        ends = ('to',) if about == [r['from']] else ('from',) if about == [r['to']] else ('from', 'to')
        text, left, misses = _join(r, ends, types, bundle, graph, aliases, stats[r['key']])
        tail = f'。{misses}' if misses else ''
        item_id = f'unlinked:{r["key"]}'
        refs = [item_id] if left and item_id in listed else []
        answer = answers.get(item_id) if refs else None
        if not left:
            out.append(_code('join', text + tail))
        elif answer is None:
            out.append(_code('join', f'{text}。连不上的行怎么处理还没说清{tail}', refs))
        else:
            reply = REPLIES[answer['choice']] + (f'（{answer["text"]}）' if answer['text'] else '') if answer['choice'] else f'客户答复：{answer["text"]}'
            out.append(_client('join', f'{text}。{reply}{tail}', [answer], refs))
    return out


def _missing_columns(d: dict, bundle: dict) -> list:
    """The columns a measure is written over that the data of this version does not have."""
    out = []
    for field in dict.fromkeys(f['field'] for term in d['terms'] for f in term['factors']):
        source, _, path = field.partition('.')
        if not _path_exists(bundle['sources'].get(source, {}).get('records', []), path):
            out.append(path)
    return out


def _computed(derived: list, kept: dict, bundle: dict) -> list:
    out = []
    for d in derived:
        if d['type'] not in kept:
            continue
        gone = _missing_columns(d, bundle)
        note = f'；这一版数据里没有{"、".join(map(quote, gone))}，编排前先核对' if gone else ''
        out.append(_person('computed', f'在{kept[d["type"]].get("label") or d["type"]}上加计算列{quote(d["label"])} = {formula_text(d)}{note}',
                           None, d.get('confirmed_at')))
    return out


def _checks(rules: list, kept: dict) -> list:
    out = []
    for rule in rules:
        if rule['type'] not in kept:   # the ontology has no such object any more: nothing to check
            continue
        what = f'{quote(rule["field"])}每个对象都有值' if rule['kind'] == 'required' else f'{quote(rule["before"])}不晚于{quote(rule["after"])}'
        found = rule.get('violations')
        state = f'这次没法检查：{rule["unchecked"]}' if found is None else \
            f'现在有 {_num(found["count"])} 个对象不满足' + (f'（例：{"、".join(found["examples"])}）' if found['count'] else '')
        out.append(_person('check', f'编排后检查{kept[rule["type"]].get("label") or rule["type"]}的{what}；{state}', None, None, [rule['id']]))
    return out


def _blank_cells(card: dict) -> list:
    """The cells of the card nobody has answered, one entry per table."""
    objects = {o['id']: o for o in card['objects']}.values()
    out = []
    for t in card['tables']:
        asks = [('一行是什么', t['grain']['id'])] if _blank(t['grain']['answer']) else []
        asks += [(f'日期列{quote(d["field"])}是什么时间', d['id']) for d in t['dates'] if _blank(d['answer'])]
        asks += [(f'数值列{quote(a["field"])}能不能相加', a['id']) for a in t['amounts'] if _blank(a['answer'])]
        asks += [(f'{o["label"]}全不全', o['id']) for o in objects if _blank(o['answer']) and o['id'].partition(':')[2].partition('|')[0] == t['source']]
        if asks:
            out.append(_code('card_blank', f'{t["source"]}：口径卡还有 {_num(len(asks))} 格没说清：{"、".join(text for text, _ in asks)}', [i for _, i in asks]))
    return out


def pipeline_spec(run: dict, bundle: dict, graph: dict, card: dict, stored: dict, derived: list, rules: list, at: str) -> dict:
    """The requirements of a kept table run whose ontology passed verification. `card` is its data-meaning card with
    the stored answers (ontology_card.build_card), `stored` the card file ({cells, items, history}), `derived` the
    measures a person confirmed, `rules` the adopted rules checked against this data (rule_discovery.check_rules) and
    `at` the time it is made. Objects and relations a person judged wrong are left out."""
    reviewed = normalize_proposal(without_wrong(run['ontology'], (run.get('confirmation') or {}).get('decisions')))
    kept = {t['key']: t for t in reviewed['object_types']}
    fit = (run.get('evaluation') or {}).get('data_fit') or {}
    profiles = {p['name']: p for p in source_profile(bundle)}
    objects = list({o['id']: o for o in card['objects']}.values())
    listed = open_items(run, bundle, graph, card)
    open_, _ = split_answers(listed, stored['items'])
    # the data check's counts as the open items read them; a relation it has no entry for is counted now
    stats = {**{s['key']: s for s in _relations(reviewed, bundle, graph)}, **{s['key']: s for s in fit.get('relations') or []}}
    return {'file': run['file']['name'], 'saved_as': run['saved_as'], 'generated_at': at,
            'tables': [_table(t, profiles[t['source']], bundle['sources'][t['source']]['records'], kept, objects, fit, run) for t in card['tables']],
            'relations': _joins(reviewed, bundle, graph, _alias_map(run['ontology']), stats, stored['items'], {i['id'] for i in listed}),
            'derived': _computed(derived, kept, bundle), 'rules': _checks(rules, kept),
            'open': [*_blank_cells(card), *(_code('open_item', i['ask'], [i['id']]) for i in open_ if i['kind'] in CHOICES)]}


def _origin(e: dict) -> str:
    if e['source'] == 'code':
        return '代码查出'
    if e['source'] == 'client':
        who = '，'.join(x for x in (e.get('by'), e.get('basis'), e['at'][5:10]) if x)
        return '客户答复' + (f'：{who}' if who else '')
    return '人确认' + (f'：{e["by"]}' if e.get('by') else '')


def pipeline_markdown(spec: dict) -> str:
    asked = sum(len(t['items']) for t in spec['tables']) + len(spec['relations']) + len(spec['derived']) + len(spec['rules'])
    lines = [f'# 编排需求单：{spec["file"]}', '', '这份清单由 OntoPoc 按数据和客户答复生成，只描述要做什么，不执行加工。', '',
             f'共 {len(spec["tables"])} 张表，{asked} 条要求，{len(spec["open"])} 条还没说清。']
    bullet = lambda e: f'- {e["text"]}（{_origin(e)}）'
    for t in spec['tables']:
        lines += ['', f'## {t["source"]}（{_num(t["rows"])} 行）', '', *([f'对象：{"、".join(t["objects"])}', ''] if t['objects'] else []), *map(bullet, t['items'])]
    for title, key in (('表之间怎么关联', 'relations'), ('计算列', 'derived'), ('编排后的校验', 'rules')):
        if spec[key]:
            lines += ['', f'## {title}', '', *map(bullet, spec[key])]
    if spec['open']:
        lines += ['', '## 还没说清的', '', *(f'- {e["text"]}' for e in spec['open'])]
    return '\n'.join(lines) + '\n'


def pipeline_files(spec: dict) -> dict[str, str]:
    """file name -> text: the document as Markdown to read and as JSON to work from."""
    return {FILES[0]: pipeline_markdown(spec), FILES[1]: json.dumps(spec, ensure_ascii=False, indent=1) + '\n'}

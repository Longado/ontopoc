"""What is still to be settled with the client, read from a kept run and its rows. Code only, no model call: the page,
the minutes and the MCP tools all read this one list, so none of them counts anything on its own. Each item carries a
sentence a consultant can say to the client (the numbers and names are put in by templates), the facts behind it, and
where in the product the answer is to be looked at or given. Each item has an id made from the thing itself, so the
same thing has the same id on the next run; the client's answer to an item is kept under that id."""
from __future__ import annotations

import re

from ontology_poc_generator.code_meanings import PATTERN_ROWS
from ontology_poc_generator.name_checks import STAT_WORDS, name_vs_calculation
from ontology_poc_generator.object_rows import _display, _labeller
from ontology_poc_generator.ontology_card import MAX_BASIS, MAX_NOTE, CardError, blank_by_table, check_by, clean_text, complete_id
from ontology_poc_generator.ontology_confirm import without_wrong
from ontology_poc_generator.ontology_eval import _row_owners
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal, normalize_value
from ontology_poc_generator.repeated_keys import EXAMPLES as REPEAT_EXAMPLES, applicable, repeated_keys, unmet
from ontology_poc_generator.review_stack import MODES, REPLY_SAYS, RECORDED, anchor_changes, anchor_of, card_replies, code_check, code_examples, example_rows, menu

MAX_MERGED = 3      # groups of an answer listed; the rest is in the check pack
MAX_SAME_NAME = 5   # groups of one type listed; all of them are counted
MAX_IDS = 5
SHARED_NAME_SHARE = 10   # a name field is the objects' own when no more than 1 in this many named objects shares a name
MAX_EXAMPLES = 3
UNANSWERED = ('query_limit', 'ontology_gap')
COLUMNS_SHOWN = 5   # blank columns named on a table's line of the card item
# what a client can say to close an item, per kind: the choices it offers (none: only words). The other kinds are settled
# by doing something, and say what.
CHOICES = {'unlinked': ('expected', 'incomplete'), 'same_name': ('distinct', 'same'), 'merged': ('distinct', 'same'),
           'found_elsewhere': (), 'unstable': (), 'check_finding': (), 'data_gap': (), 'data_gaps': (), 'unanswered': (),
           'name_vs_calc': ('rename', 'name_right'), 'name_source': (), 'name_by_view': (), 'name_values': ()}
BY_DOING = {'model_filter': '要去掉条件重算，或替换验收题', 'unjudged': '要逐项判对错', 'card_blank': '要把口径卡填完',
            'code_meaning': '要在这件事里逐个填上代码的含义，再点“确认含义”', 'repeated_key': '要选一种处理办法，再点“确认”'}
CHOICE_SAYS = {'expected': '本来就没有对应，属正常', 'incomplete': '数据没导全', 'distinct': '是不同的对象', 'same': '是同一个',
               'rename': '名字说错了，按实际算法改名', 'name_right': '名字是对的，是数据算得不对'}


def _num(value) -> str:
    """Thousands separators and two decimals at most: 4176392.96 -> 4,176,392.96, 1308.0 -> 1,308."""
    if abs(float(value)) >= 1e15:   # 1e308 is not printed as 309 digits
        return f'{float(value):.4g}'
    return f'{int(value):,}' if float(value).is_integer() else f'{value:,.2f}'.rstrip('0').rstrip('.')


def _item(kind: str, ask: str, target: dict, facts=(), from_model: bool = False, **extra) -> dict:
    return {'kind': kind, 'ask': ask, 'facts': list(facts), 'from_model': from_model, 'target': target, **extra}


def _questions(evaluation: dict) -> tuple[dict, dict]:
    """Each question once, as (item, where it sits): the accepted version when there is one, else the latest ask. The
    model's own round of questions is not the client's and is left out. Also each question's latest ask: one asked
    again shows the edit."""
    asked = {}
    for ask_round in evaluation.get('asked') or []:
        for item in ask_round.get('items') or []:
            asked[item['question']] = item
    questions = {q: (item, 'ask') for q, item in asked.items()}
    for item in (evaluation.get('acceptance') or {}).get('items') or []:
        questions[item['question']] = (item, 'acceptance')
    return questions, asked


def _found_elsewhere(item: dict) -> list:
    return (item.get('evidence') or {}).get('found_elsewhere') or []


def _qa_target(place: str, question: str) -> dict:
    return {'tab': 'qa', 'place': place, 'question': question}


def _bare(field) -> str:
    """A field as the check pack names it: the query may put its table in front ("orders.地区")."""
    return str(field).partition('.')[2] or str(field)


def _model_filters(questions: dict, asked: dict, label) -> list:
    out = []
    for question, (item, place) in questions.items():
        dropped = ((asked.get(question) or {}).get('edited') or {}).get('dropped') or [] if place == 'acceptance' else []
        if item['status'] != 'answered' or not isinstance(item.get('query'), dict) or (place == 'acceptance' and item.get('note')):
            continue   # a person who wrote the basis down has already settled what the question means; an answer read from a relation check has no query to look at
        start = label(item['query']['start'])
        measure = ((item.get('answer') or {}).get('measure') or {}).get('field')
        for f in (item.get('evidence') or {}).get('filters') or []:
            removed = f['before'] - f['after']
            if not f.get('not_in_question') or removed <= 0:
                continue
            amount = f'，这些行的“{measure}”合计 {_num(f["removed_measure"])}' if measure and 'removed_measure' in f else ''
            ask, here = (f'「{question}」的答案里，模型自己加了条件“{f["field"]} = {f["equals"]}”，问题里没提。'
                         f'它筛掉了 {_num(removed)} 个{start}{amount}。这个条件该不该加？'), place
            requeried = any(_bare(d['field']) == _bare(f['field']) and d['equals'] == f['equals'] for d in dropped)
            if requeried:
                # already asked again without it: what is left is whether the new answer takes the accepted one's place
                ask, here = (f'「{question}」去掉模型加的条件“{f["field"]} = {f["equals"]}”重算过了，'
                             '验收题里存的还是带这个条件的答案。要换成新答案吗？'), 'ask'
            facts = [f'筛选前 {_num(f["before"])} 个{start}，筛选后 {_num(f["after"])} 个',
                     *([f'被筛掉的有：{"、".join(f["examples"])}'] if f.get('examples') else [])]
            out.append(_item('model_filter', ask, _qa_target(here, question), facts, question=question,
                             id=f'model_filter:{question}|{_bare(f["field"])}={f["equals"]}',
                             filter={k: f[k] for k in ('field', 'equals', 'before', 'after', 'removed_measure') if k in f},
                             **({'requeried': True} if requeried else {})))
    return out


def _merged(questions: dict) -> list:
    out = []
    for question, (item, place) in questions.items():
        if item['status'] != 'answered':
            continue
        for g in ((item.get('evidence') or {}).get('merged') or [])[:MAX_MERGED]:
            more = '等' if g['objects'] > len(g['examples']) else ''
            ask = (f'「{question}」的答案里，“{g["group"]}”这一组下有 {_num(g["objects"])} 个不同的{g["reached"]}'
                   f'（{"、".join(g["examples"])}{more}），按同一个算了。它们是同一个吗？')
            out.append(_item('merged', ask, _qa_target(place, question),
                             [f'{_num(g["starts"])} 个{g["start"]}落在“{g["group"]}”这一组里'], question=question, id=f'merged:{question}|{g["group"]}'))
    return out


def _elsewhere(questions: dict, label) -> list:
    out = []
    for question, (item, place) in questions.items():
        found = _found_elsewhere(item) if item['status'] == 'no_data' and isinstance(item.get('query'), dict) else []
        if not found:
            continue
        start = label(item['query']['start'])
        by_value = {}
        for e in found:
            by_value.setdefault(e['equals'], []).append(e)

        def where(e):
            here = f'{label(e["type"])}里有' + (f' {_num(e["count"])} 个' if e['count'] > 1 else '')
            return here + (f'，{_num(e["linked"])} 个{start}连着它' if e['linked'] else f'，但没有{start}连着它')
        said = '。'.join(f'找不到“{value}”，但' + '；'.join(map(where, es)) for value, es in by_value.items())
        facts = []
        for value, es in by_value.items():
            facts.append(f'条件“{es[0]["field"]} = {value}”在{start}里没有一个对象满足')
            facts += [f'{label(e["type"])}里有 {_num(e["count"])} 个对象的编号含“{value}”，'
                      + (f'其中连着 {_num(e["linked"])} 个{start}' if e['linked'] else f'没有{start}连着它们') for e in es]
        asked_about = '、'.join(dict.fromkeys(label(e['type']) for e in found))
        out.append(_item('found_elsewhere', f'「{question}」在{start}里{said}。这道题问的是不是{asked_about}？',
                         _qa_target(place, question), facts, question=question, id=f'found_elsewhere:{question}'))
    return out


def _unlinked(fit: dict, types: dict, relations: dict, kept: dict, label, relation_name, owners: dict) -> list:
    orphans = {o['type']: o for o in fit.get('orphans') or []}
    out = []
    for stat in fit.get('relations') or []:
        left = stat['rows'] - stat['linked_rows']
        if left <= 0 or stat['key'] not in kept['relations']:
            continue
        r = relations[stat['key']]
        # the end the table is about (an order table read for its customer too is still about orders), else the first read there
        reads = [k for k in (r['from'], r['to'], *types) if any(pop['source'] == stat['source'] for pop in types[k]['populated_from'])]
        owner = next((k for k in reads if k in owners.get(stat['source'], ())), reads[0] if reads else None)
        table = f'{label(owner)}（{stat["source"]}）' if owner else f'{stat["source"]} '
        other = r['from'] if owner == r['to'] else r['to']
        ask = (f'{table}{_num(stat["rows"])} 行里有 {_num(left)} 行没连上“{relation_name(r)}”。'
               f'是这些行本来就没有对应的{label(other)}，还是数据没导全？')
        examples = (orphans.get(r['from']) or {}).get('examples')
        facts = [*([f'没连上任何对象的{label(r["from"])}，例如 {"、".join(examples)}'] if examples else []),
                 *([f'其中 {_num(stat["empty_rows"])} 行用来连的编号是空的'] if stat.get('empty_rows') else [])]
        out.append(_item('unlinked', ask, {'tab': 'graph', 'relation': r['key']}, facts, relation=r['key'], id=f'unlinked:{r["key"]}',
                         complete_id=complete_id(types[other]), check={'status': 'failed', 'text': f'连得上 {_num(stat["linked_rows"])} / {_num(stat["rows"])} 行'},
                         anchor={'noun': '内容', 'members': [], 'counts': {'没连上的行': left}, 'total': stat['rows']}))
    return out


def _same_name(p: dict, bundle: dict, graph: dict, kept: dict, label) -> list:
    out = []
    for t in (t for t in p['object_types'] if t['key'] in kept['types']):
        display = _display(t)
        if display is None or display in {path for pop in t['populated_from'] for path in pop['identity'].values()}:
            continue   # shown by a part of its own number: the same name cannot come with another number
        describe = _labeller(t, bundle, graph['records_of'])
        groups = {}
        for inst in (i for i in graph['records_of'] if i[0] == t['key']):
            number, name, _ = describe(inst)
            if normalize_value(name):
                groups.setdefault(normalize_value(name), []).append((name, number))
        same = [g for g in groups.values() if len(g) > 1]
        # an order's name field is the receiver's, which all one customer's orders share: names that many objects share are not the objects' own
        if not same or sum(map(len, same)) * SHARED_NAME_SHARE > sum(map(len, groups.values())):
            continue

        def numbers(g):
            return ' / '.join(n for _, n in g[:MAX_IDS]) + (f' 等 {len(g)} 个' if len(g) > MAX_IDS else '')
        name = label(t['key'])
        ask = (f'{name}里有 {_num(len(same))} 组名字相同、编号不同，例如 {same[0][0][0]}（{numbers(same[0])}）。'
               f'它们是同一个{name}的不同主体，还是该合并？')
        out.append(_item('same_name', ask, {'tab': 'objects', 'object': t['key']},
                         [f'{g[0][0]}：{numbers(g)}' for g in same[:MAX_SAME_NAME]], id=f'same_name:{t["key"]}'))
    return out


def _unstable(stability: dict, relations: dict, kept: dict, label, relation_name) -> list:
    runs = stability.get('runs')
    target = {'tab': 'objects', 'place': 'stability'}
    out = []
    for key, seen in (stability.get('relations') or {}).items():
        if seen < runs and key in kept['relations']:
            out.append(_item('unstable', f'关系“{relation_name(relations[key])}”在 {runs} 次建模里只出现了 {seen} 次。这条关系要保留吗？',
                             target, [f'共建模 {runs} 次，这条关系出现了 {seen} 次'], relation=key, id=f'unstable:relation:{key}'))
    for key, seen in (stability.get('types') or {}).items():
        if seen < runs and key in kept['types']:
            out.append(_item('unstable', f'对象“{label(key)}”在 {runs} 次建模里只出现了 {seen} 次。这类对象要保留吗？',
                             target, [f'共建模 {runs} 次，这类对象出现了 {seen} 次'], id=f'unstable:type:{key}'))
    elsewhere = stability.get('elsewhere') or {}
    for kind, word in (('relations', '关系'), ('types', '对象')):
        for found in elsewhere.get(kind) or []:
            out.append(_item('unstable', f'另外 {found["count"]} 次建模里出现过{word}“{found["label"]}”，这次的本体里没有。要不要加？',
                             target, [f'共建模 {runs} 次，另外 {found["count"]} 次出现了它'], id=f'unstable:new:{kind}:{found["label"]}'))
    return out


def _check_findings(fit: dict, kept: dict, label, relations: dict, settled: frozenset | set = frozenset()) -> list:
    quote = lambda v: f'“{v}”'

    def missing(x):
        shown = '、'.join(x['examples'][:MAX_EXAMPLES])
        if 'relation' in x:
            more = '等' if x['count'] > len(x['examples'][:MAX_EXAMPLES]) else ''
            via = relations[x['relation']].get('label') or x['relation']
            return f'{label(x["type"])}在 {x["source"]} 表里被“{via}”引用却不存在：{shown}{more}，共 {_num(x["count"])} 个'
        return f'{label(x["type"])}在 {x["source"]} 表里缺 {shown}' + (f' 等 {_num(x["count"])} 个' if x['count'] > MAX_EXAMPLES else '')
    # data_fit key, how many it counts, what is said about them, the question, one line per finding
    specs = (
        ('identity_conflicts', len, '处同一个对象在原表的不同行里取值不一样', '以哪个为准？',
         lambda x: f'{label(x["type"])} {x["identity"]} 的“{x["field"]}”：{" / ".join(x["values"])}'),
        ('identity_spellings', len, '个对象的编号写法不止一种，系统已按同一个算', '这样合并对吗？',
         lambda x: f'{label(x["type"])} {x["identity"]}：{" / ".join(map(quote, x["variants"]))}'),
        ('suspected_duplicates', len, '组编号只差前面的 0，目前算成了不同对象', '它们是同一个吗？',
         lambda x: f'{label(x["type"])}：{" / ".join(x["identities"])}'),
        ('missing_across_sources', lambda xs: sum(x['count'] for x in xs), '个对象被别的表提到，却不在描述它们的表里', '这些数据能补上吗？', missing),
        ('identity_risks', len, '类对象只靠名称一类的字段识别', '改名或写法一变就会被当成另一个对象，有没有编号可用？',
         lambda x: f'{label(x["type"])}：只靠{"、".join(map(quote, x["fields"]))}识别'),
        ('unused_sources', len, '张上传的表没被本体读取', '是漏了还是确实用不上？',
         lambda x: f'“{x["source"]}”表：{_num(x["rows"])} 行、{_num(x["fields"])} 个字段'))
    out = []
    for key, count, said, question, line in specs:
        # unused tables have no type; a missing object found through a relation goes with the relation
        found = [x for x in fit.get(key) or [] if ('type' not in x or x['type'] in kept['types'])
                 and ('relation' not in x or x['relation'] in kept['relations'])
                 and not (key == 'identity_conflicts' and (x['type'], x['source'], x['identity']) in settled)]
        if found:
            lines = [line(x) for x in found[:MAX_EXAMPLES]]
            out.append(_item('check_finding', f'有 {_num(count(found))} {said}，例如{lines[0]}。{question}', {'tab': 'check'}, lines, id=f'check_finding:{key}'))
    return out


GENERIC_COLUMNS = frozenset({'日期', '时间', '金额', '名称', '名字', '数量', '编号', '类型', '状态', '备注'})   # a word any sentence about data uses
MISSING = re.compile(r'(缺少|缺失|缺乏|没有|无(?![法需效]))[^，。,;；]*$')   # "缺少付款日期": what the sentence names is what is absent
MEANING = re.compile(r'的?(字典|含义|说明|解释|释义|定义)')   # "没有状态码的字典": what is absent is the column's meaning, not the column


def _repeated_keys(ontology: dict, bundle: dict, graph: dict, kept: dict, label) -> list:
    """One item per (object type, table) whose key repeats in the table describing the object, until a person has chosen
    how the rows are read (bundle['repeat_rules'], kept by the server). Each shows the first few identities with their
    rows and the columns on which the rows differ."""
    chosen = bundle.get('repeat_rules') or {}
    out = []
    for g in repeated_keys(ontology, bundle, graph):
        if g['type'] not in kept['types'] or applicable(g, chosen.get(g['rule_key'])):
            continue
        shown = g['objects'][:REPEAT_EXAMPLES]
        lines = [f'{o["identity"]}：{len(o["rows"])} 行' + ''.join(f'，{c}：{" / ".join(v)}' for c, v in o['differs']) for o in shown]
        # a choice made before that this data no longer carries out (the column is gone, or a new key repeats) is asked again, and says so
        again = unmet(g, chosen.get(g['rule_key'])) or ''
        ask = (f'{again}{label(g["type"])}（{g["source"]}表）里有 {_num(len(g["objects"]))} 个编号出现在不止一行，共 {_num(g["rows"])} 行，'
               f'例如 {shown[0]["identity"]}。这些行怎么算：每一行都留、只留最新的，还是当作数据错误？')
        records = bundle['sources'][g['source']]['records']
        out.append(_item('repeated_key', ask, {'tab': 'objects', 'object': g['type']}, lines, id=g['id'],
                         repeat={'type': g['type'], 'source': g['source'], 'identities': len(g['objects']), 'rows': g['rows'], 'columns': g['latest_columns']},
                         examples=example_rows(g['source'], records, shown[0]['rows'], [*list(records[0])[:1], *(c for c, _ in shown[0]['differs'])]),   # the table's first column (its key, usually), then where the rows differ
                         check={'status': 'failed', 'text': f'编号唯一性没通过：{_num(len(g["objects"]))} 个编号出现在不止一行，共 {_num(g["rows"])} 行'},
                         anchor={'noun': '重复的编号', 'members': [o['identity'] for o in g['objects']]}))
    return out


def _settled_repeats(ontology: dict, bundle: dict, graph: dict) -> set:
    """(object type, table, identity) of the keys on more than one row that a person has already decided about: the
    check of the data found the rows disagreeing too, and asking "which one is right?" again would ask the same thing."""
    chosen = bundle.get('repeat_rules') or {}
    return {(g['type'], g['source'], o['identity']) for g in repeated_keys(ontology, bundle, graph)
            if applicable(g, chosen.get(g['rule_key'])) for o in g['objects']}


def _columns_named(sentence: str, bundle: dict) -> list[tuple[str, str]]:
    """(table, column) for every column of an uploaded table the sentence names. A name of one character is too easily a
    word in the sentence; a name inside a longer one that is also named ("金额" in "订单金额") is not a second column;
    when the sentence names a table, only that table's columns count."""
    pairs = [(s, c) for s, t in bundle['sources'].items() for c in dict.fromkeys(k for r in t['records'] for k in r) if len(c) >= 2 and c in sentence]
    named = {c for _, c in pairs}
    pairs = [(s, c) for s, c in pairs if not any(c != other and c in other for other in named)]
    in_tables = [(s, c) for s, c in pairs if s in sentence]
    return in_tables or pairs


def _firm(sentence: str, column: str) -> bool:
    """A name in a sentence says the sentence is about that column only when the name is not a word any sentence about
    data uses (日期, 金额) and the sentence does not name it as the thing that is absent ("缺少付款日期"); a missing word
    before the name is harmless when it is the column's dictionary or meaning that is said to be missing."""
    end = sentence.index(column) + len(column)
    return column not in GENERIC_COLUMNS and (bool(MEANING.match(sentence, end)) or not MISSING.search(sentence[:end]))


def _column_facts(bundle: dict, table: str, column: str) -> str:
    records = bundle['sources'][table]['records']
    filled = [r[column] for r in records if r.get(column) not in (None, '')]
    return f'{table}：{_num(len(records))} 行，「{column}」{_num(len(records) - len(filled))} 行为空，{_num(len(set(filled)))} 个不同取值'


def _gap_ties(ontology: dict, bundle: dict) -> tuple[dict, list]:
    """The model's data gaps sorted: {column: [(sentence, tables)]} for the sentences that firmly name a column of an
    uploaded table, and the rest as text (a sentence that only weakly names one says "可能与「X」有关" and nothing more)."""
    tied: dict[str, list] = {}
    plain = []
    for sentence in ontology.get('data_gaps') or []:
        named = _columns_named(sentence, bundle)
        firm = [(t, c) for t, c in named if _firm(sentence, c)]
        for column in dict.fromkeys(c for _, c in firm):
            tied.setdefault(column, []).append((sentence, [t for t, c in firm if c == column]))
        if not firm:
            weak = '、'.join(f'「{c}」' for c in dict.fromkeys(c for _, c in named))
            plain.append(f'{sentence}（可能与{weak}有关）' if weak else sentence)
    return tied, plain


def _data_gaps(tied: dict, plain: list, bundle: dict, coded: frozenset) -> list:
    """The model's data gaps. One that names a column of an uploaded table is an item about that column (several sentences
    about one column are one item), with what the data says about the column beside it; the others stay together as text.
    A column that has a code-meaning item has the sentence on that item (see _code_meanings), so it is left out here.
    Matching a name in a sentence is code's; whether the gap is real is the model's word, and the item says so."""
    out = []
    for column, found in tied.items():
        found = [(s, [t for t in ts if (t, column) not in coded]) for s, ts in found]
        found = [(s, ts) for s, ts in found if ts]
        if not found:
            continue
        tables = list(dict.fromkeys(t for _, ts in found for t in ts))
        sentences = list(dict.fromkeys(s for s, _ in found))
        said = '”“'.join(sentences)
        out.append(_item('data_gap', f'模型指出“{said}”，说的是「{column}」这一列。客户那边有没有能补上的数据？',
                         {'tab': 'data', 'table': tables[0]}, [_column_facts(bundle, t, column) for t in tables], from_model=True, id=f'data_gap:{column}'))
    if plain:
        out.append(_item('data_gaps', f'模型指出 {_num(len(plain))} 处数据缺口（下面逐条）。客户那边有没有能补上的数据？',
                         {'tab': 'objects', 'place': 'build'}, plain, from_model=True, id='data_gaps'))
    return out


def _unanswered(questions: dict) -> list:
    stuck = [(q, item) for q, (item, _) in questions.items()
             if item['status'] in UNANSWERED or (item['status'] == 'no_data' and not _found_elsewhere(item))]
    if not stuck:
        return []
    facts, from_model = [], False
    for question, item in stuck:
        if item['status'] == 'no_data':
            why = '数据里没有'
        elif item.get('reason_from_model') or not isinstance(item.get('query'), dict):
            # ask_questions gives a question with no query only the model's own reason; an accepted copy loses the flag
            from_model = True
            why = '查询写不出来（模型的判断）' if item['status'] == 'query_limit' else '本体缺回答它要的东西（模型的判断）'
        else:
            why = item['reason']
        facts.append(f'「{question}」：{why}')
    return [_item('unanswered', f'{_num(len(stuck))} 道问过的题现在答不了。这次 POC 要不要答它们？',
                  {'tab': 'qa', 'place': 'ask'}, facts, from_model, id='unanswered')]


def _card_blank(card: dict | None) -> list:
    """The cells of the data-meaning card nobody has answered (or answered "unsure"), table by table."""
    if not card or not card['blank']:
        return []
    tables = blank_by_table(card)

    def line(source, n, columns):
        shown = '、'.join(columns[:COLUMNS_SHOWN]) + ('等' if len(columns) > COLUMNS_SHOWN else '')
        return f'{source}：{_num(n)} 格' + (f'（{shown}）' if columns else '')
    ask = (f'口径卡还有 {_num(card["blank"])} 格没说清（{_num(len(tables))} 张表）：'
           '数值列能不能相加、日期列是什么时间、一行是什么、对象全不全。会上逐张过一遍？')
    return [_item('card_blank', ask, {'tab': 'card'}, [line(*t) for t in tables], id='card_blank')]


def _code_meanings(codes: dict | None, tied: dict | None = None) -> list:
    """One item per code column that still has a value nobody gave a meaning. codes: {profiles: code_meanings.code_columns,
    enums: the confirmed meanings by field, drafts: the model's guesses by item id}. Each value carries its counts and the
    facts that set it against the other columns; a model's guess comes with whether the data backs it (strong: another
    column tells this value's own rows from the other values' rows) and, when it does not, why (few_rows, no_pattern);
    it is only pre-selected when it does. tied: the model's data-gap sentences by the column they firmly name; the ones about
    this column are put among its facts, so the column is one item, not two."""
    out = []
    for profile in (codes or {}).get('profiles') or []:
        confirmed = {e['value']: e for e in ((codes['enums'].get(profile['field']) or {}).get('values') or [])}
        if all(v['value'] in confirmed for v in profile['values']):
            continue
        guesses = codes['drafts'].get(profile['id']) or {}
        values = []
        for v in profile['values']:
            guess = guesses.get(v['value'])
            strong = v['pattern']   # the pattern already needs enough rows under this value and under the others
            rest = profile['rows'] - profile['blank'] - v['rows']
            weak = None if strong else 'few_rows' if min(v['rows'], rest) < PATTERN_ROWS else 'no_pattern'
            held = ((codes.get('waiting') or {}).get(profile['field']) or {}).get('values', {}).get(v['value'])   # confirmed before the data changed, waiting for a second look: starts in the box, not as confirmed
            values.append({**v, 'confirmed': {k: confirmed[v['value']][k] for k in ('label', 'description')} if v['value'] in confirmed else None,
                           'waiting': held,
                           'recommendation': {**guess, 'strong': strong, 'why_weak': weak} if guess else None,
                           'preselected': bool(guess) and strong and v['value'] not in confirmed})
        shown = '、'.join(v['value'] for v in values)
        said = [f'模型指出：“{sentence}”（模型的说法）' for sentence, tables in (tied or {}).get(profile['column'], []) if profile['source'] in tables]
        facts = [f'取值 {v["value"]}：' + '；'.join(v['facts']) for v in values] + said
        out.append(_item('code_meaning', f'「{profile["source"]}」的「{profile["column"]}」是代码，共 {_num(len(values))} 个取值（{shown}），'
                         '数据里没有写它们是什么意思。每个代码指什么？',
                         {'tab': 'data', 'table': profile['source']}, facts, from_model=False, id=profile['id'],
                         column={'source': profile['source'], 'column': profile['column'], 'field': profile['field'], 'rows': profile['rows'],
                                 'values': values},
                         check=code_check(values),
                         anchor={'noun': '取值', 'members': [v['value'] for v in values], 'counts': {f'取值 {v["value"]}': v['rows'] for v in values}, 'total': profile['rows']}))
    return out


def _statistic(kind: str) -> str:
    return STAT_WORDS.get(kind) or f'第 {kind[1:]} 百分位'


def _how(kind: str) -> str | None:
    """How a percentile other than the median is worked out, for the page that shows the evidence (not in the rows read aloud)."""
    return f'第 {kind[1:]} 百分位按插值算；写成“最近秩”（取排在 {kind[1:]}% 位置上的那个数）的也算对' if kind.startswith('p') else None


def _name_vs_calc(ontology: dict, bundle: dict) -> list:
    """A column whose name claims a statistic (P50, 平均, 合计) that its source rows do not give: one item per column, with the row by
    row comparison. Code does the comparison (see name_checks); whether the name or the numbers are wrong is the client's to say.
    Three other things are asked rather than left unsaid: which table to work it out from when two have the column, what to
    call a column that is right over a confirmed view (有效订单) and not over the whole table, and what a value that is not a
    number (N/A) in the claiming column is."""
    out = []
    for f in name_vs_calculation(ontology, bundle):
        says = _statistic(f['says'])
        written_bad = ([f'「{f["table"]}」的「{f["column"]}」自己有 {_num(f["written_unreadable"])} 个值不是数字（如{"、".join(f["written_unreadable_shown"])}），没有和重算的{says}比']
                       if f.get('written_unreadable') else [])
        too_large = [f'{_num(f["too_large"])} 行的重算值大到不是数字，没有比'] if f.get('too_large') else []
        notes = [*written_bad, *too_large]
        head = {'source': f['table'], 'column': f['column'], 'says': f['says'], 'says_text': says}
        target = {'tab': 'data', 'table': f['table']}
        if f.get('candidates'):
            names = '、'.join(f'「{c}」' for c in f['candidates'])
            out.append(_item('name_source', f'「{f["table"]}」的「{f["column"]}」名字说是{says}，但{names}都有「{f["source_column"]}」，没法确定用哪一张重算。该用哪一张？',
                             target, id=f'name_source:{f["table"]}.{f["column"]}', column={**head, 'candidates': f['candidates']}))
        elif f['view']:
            out.append(_item('name_by_view', f'「{f["table"]}」的「{f["column"]}」不是用「{f["source"]}」的全部行算的{says}，是按「{f["view"]}」算的{says}。名字要不要写明？',
                             target, [f'{f["compared"]} 行全部和按「{f["view"]}」重算的{says}对得上，按全部行算有 {_num(f["mismatched"])} 行对不上', *notes],
                             id=f'name_by_view:{f["table"]}.{f["column"]}', column={**head, 'view': f['view']}))
        elif f['mismatched']:
            actual = f'，这些行算出来都是{STAT_WORDS[f["actual"]]}' if f['actual'] else ''
            ask = (f'「{f["table"]}」的「{f["column"]}」名字说是{says}，用「{f["source"]}」的「{f["source_column"]}」按{"、".join(f["by"])}重算，'
                   f'{_num(f["compared"])} 行里有 {_num(f["mismatched"])} 行对不上{actual}。名字对，还是该改名？')
            facts = [f'「{f["source"]}」的「{f["source_column"]}」有 {_num(f["unreadable"])} 个值不是数字（如{"、".join(f["unreadable_shown"])}），没有算进去'] if f['unreadable'] else []
            facts += notes
            facts += [f'{r["key"]}：写的是 {_num(r["written"])}，{says}应是 {_num(r["computed"][f["says"]])}'
                      + (f'，{"、".join(STAT_WORDS[k] for k in r["agrees_with"])}是 {_num(r["computed"][r["agrees_with"][0]])}' if r['agrees_with'] and not r['agrees'] else '')
                      for r in f['rows'] if not r['agrees']]
            out.append(_item('name_vs_calc', ask, target, facts, id=f'name_vs_calc:{f["table"]}.{f["column"]}',
                             column={**head, 'actual': f['actual'], 'actual_text': STAT_WORDS.get(f['actual']), 'how': _how(f['says'])},
                             check={'status': 'failed', 'text': f'重算{says}，{_num(f["compared"])} 行里 {_num(f["mismatched"])} 行对不上'},
                             anchor={'noun': '内容', 'members': [], 'counts': {'对不上的行': f['mismatched']}, 'total': f['compared']}))
        elif written_bad:
            out.append(_item('name_values', f'「{f["table"]}」的「{f["column"]}」名字说是{says}，其余的行和重算对得上，但有 {_num(f["written_unreadable"])} 个值不是数字'
                             f'（如{"、".join(f["written_unreadable_shown"])}），没法比。是漏填，还是写法要改？',
                             target, notes, id=f'name_values:{f["table"]}.{f["column"]}', column=head))
    return out


def _unjudged(run: dict, p: dict) -> list:
    decisions = (run.get('confirmation') or {}).get('decisions') or {}
    objects = [t for t in p['object_types'] if not (decisions.get('types') or {}).get(t['key'], {}).get('verdict')]
    links = [r for r in p['relations'] if not (decisions.get('relations') or {}).get(r['key'], {}).get('verdict')]
    said = '、'.join(part for part in (f'{_num(len(objects))} 个对象' if objects else '', f'{_num(len(links))} 条关系' if links else '') if part)
    return [_item('unjudged', f'{said}还没人判过对错。会上逐项过一遍？', {'tab': 'objects', 'place': 'confirm'}, id='unjudged')] if said else []


def open_items(run: dict, bundle: dict, graph: dict | None = None, card: dict | None = None, codes: dict | None = None) -> list:
    """The items for a kept table run, in the fixed order of their kinds (within a kind, in the order the data gives
    them). A run whose ontology did not pass verification has nothing to settle yet. `graph` is the run's own graph
    when the caller already holds it; `card` is its data-meaning card (ontology_card.build_card), without which there
    is no item about the card; `codes` (see _code_meanings) is what the code columns of the tables need."""
    ontology = run['ontology']
    if ontology['status'] != 'auto_built_verified':
        return []
    evaluation = run.get('evaluation') or {}
    p = normalize_proposal(ontology)
    types, relations = {t['key']: t for t in p['object_types']}, {r['key']: r for r in p['relations']}
    label = lambda key: (types.get(key) or {}).get('label') or key
    relation_name = lambda r: f'{label(r["from"])} {r.get("label") or r["key"]} {label(r["to"])}'
    questions, asked = _questions(evaluation)
    fit = evaluation.get('data_fit') or {}
    # what a person judged wrong (or a relation with a wrong end) has been settled: nothing about it is asked again
    judged = without_wrong(ontology, (run.get('confirmation') or {}).get('decisions'))
    kept = {'types': {t['key'] for t in judged['object_types']}, 'relations': {r['key'] for r in judged['relations']}}
    graph = graph or build_graph(ontology, bundle)
    tied, plain = _gap_ties(ontology, bundle)
    coded = _code_meanings(codes, tied)
    return [*_model_filters(questions, asked, label), *_merged(questions), *_elsewhere(questions, label),
            *_unlinked(fit, types, relations, kept, label, relation_name, _row_owners(judged, graph)),
            *_same_name(p, bundle, graph, kept, label),
            *_unstable(evaluation.get('stability') or {}, relations, kept, label, relation_name),
            *_check_findings(fit, kept, label, relations, _settled_repeats(ontology, bundle, graph)), *_repeated_keys(ontology, bundle, graph, kept, label), *_name_vs_calc(ontology, bundle), *coded, *_card_blank(card),
            *_data_gaps(tied, plain, bundle, frozenset((c['column']['source'], c['column']['column']) for c in coded)),
            *_unanswered(questions), *_unjudged(run, p)]


def with_replies(items: list, bundle: dict | None = None) -> list:
    """Each item as the review stack shows it: with the replies its kind offers (review_stack.menu) and, for a code column, one
    row for each of its first values from the stored table. Done where the lists are served, not in open_items, which the
    minutes and the MCP tools read as well."""
    return [{**i, 'replies': menu(i['kind']),
             **({'examples': e} if i['kind'] == 'code_meaning' and bundle and (e := code_examples(i, bundle)) else {})} for i in items]


def code_meaning_items(codes: dict) -> list:
    """Only the code-meaning items (see _code_meanings): the one kind of thing that can be settled on a run whose draft was
    blocked, since it needs the stored tables and nothing from the ontology."""
    return _code_meanings(codes)


def check_answers(listed: list, raw, by, at: str) -> dict:
    """The answers posted for items, ready to keep: {item id: answer}. `listed` is every item of the run now, open or
    answered. An entry is {"id", and one of "choice" (the kind's own) or "reply" (confirm, wrong, not_applicable, exception: see
    review_stack), "text", "basis", "mode" ('single' or 'bulk')}. A reply or choice is optional; without one the words are
    required; {"reply": "reopen"} takes an answer back. A reply that stays decided (not_applicable, exception) keeps what the item is about now, so that the next upload can tell whether it still holds. Anything wrong
    raises CardError and nothing is returned."""
    by = check_by(by)
    if not isinstance(raw, list):
        raise CardError('items 要写成列表')
    by_id = {i['id']: i for i in listed}
    out = {}
    for entry in raw:
        if not isinstance(entry, dict):
            raise CardError('每件事的答复写法不对，要写成 {"id": …, "choice": …, "text": …}')
        item = by_id.get(entry.get('id')) if isinstance(entry.get('id'), str) else None
        if item is None:
            raise CardError('这件事已经不在清单上了')
        if entry.get('reply') == 'reopen':   # a decision taken back: the item is open again (the old one stays in the card's history)
            out[item['id']] = None
            continue
        kind, choice, reply, mode = item['kind'], entry.get('choice'), entry.get('reply'), entry.get('mode', 'single')
        if kind not in CHOICES and reply not in card_replies(kind):
            raise CardError(f'这件事不能用答复来关掉：{BY_DOING.get(kind, "要照它的要求去做")}')
        if mode not in MODES:
            raise CardError('mode 只能是 single 或 bulk')
        if reply is not None and (choice is not None or reply not in card_replies(kind)):
            raise CardError('这件事的 reply 只能是：' + '、'.join(card_replies(kind)) + '，且不能和 choice 一起给' if card_replies(kind) else '这件事没有可选的 reply')
        if choice is not None and choice not in CHOICES.get(kind, ()):
            raise CardError(f'这件事的 choice 只能是：{"、".join(CHOICES[kind])}' if CHOICES.get(kind) else '这件事没有可选的答复，只能写文字')
        text, basis = clean_text(entry.get('text'), MAX_NOTE, '答复的文字'), clean_text(entry.get('basis'), MAX_BASIS, '出处')
        needs = next((m['needs_text'] for m in menu(kind) if m['id'] == reply), False)
        if needs and not text:
            raise CardError('已知例外要写原因，“不对”要写对的是什么' if reply != 'confirm' else '要写下客户怎么答的')
        if choice is None and reply is None and not text:
            raise CardError('要选一个答复，或写几个字')
        out[item['id']] = {'choice': choice, 'text': text, 'by': by, 'basis': basis, 'at': at, 'asked': item['ask'], 'mode': mode,
                           **({'reply': reply} if reply else {}), **({'anchor': anchor_of(item)} if reply in RECORDED else {})}
    return out


def linked_cells(listed: list, answers: dict, stored: dict, at: str) -> dict:
    """What an unlinked item's answer does to the card, as {cell id: answer, or None to clear it}. Answered "incomplete",
    the other end's cell (`complete_id`) is set to "only partly in the data" with the answer's words, and carries the
    item's id in `item`. Answered any other way, that cell is cleared, but only while it still is what this item wrote:
    one a person has set since is theirs. `listed` is every item of the run, `stored` the cells kept for the file."""
    by_id = {i['id']: i for i in listed}
    out = {}
    for item_id, answer in answers.items():
        cell_id = by_id[item_id].get('complete_id')
        if cell_id is None:
            continue
        if answer and answer['choice'] == 'incomplete':
            out[cell_id] = {'value': 'partial', 'note': answer['text'], 'by': answer['by'], 'basis': answer['basis'], 'at': at, 'item': item_id}
        elif (stored.get(cell_id) or {}).get('value') == 'partial' and stored[cell_id].get('item') == item_id:
            out[cell_id] = None
    return out


def split_answers(items: list, answers: dict) -> tuple[list, list]:
    """The items still open, and the ones the client has answered, each with its answer (and the words for a choice or a
    reply). An answer whose item is not on the list this time is in neither. A decision that stays decided (not applicable, an
    exception) whose anchor has broken since is open again, with the old decision and what changed in `reopened`."""
    open_, answered = [], []
    for item in items:
        got = answers.get(item['id'])
        changes = anchor_changes(got['anchor'], anchor_of(item)) if got and got.get('anchor') else []
        if got is None:
            open_.append(item)
        elif changes:
            open_.append({**item, 'reopened': {'reply': got['reply'], 'says': REPLY_SAYS[got['reply']], 'by': got['by'], 'at': got['at'], 'text': got['text'], 'changes': changes}})
        else:
            says = CHOICE_SAYS[got['choice']] if got.get('choice') else REPLY_SAYS[got['reply']] if got.get('reply') else None
            answered.append({**item, 'answer': {**got, **({'says': says} if says else {})}})
    return open_, answered

"""What is still to be settled with the client, read from a kept run and its rows. Code only, no model call: the page,
the minutes and the MCP tools all read this one list, so none of them counts anything on its own. Each item carries a
sentence a consultant can say to the client (the numbers and names are put in by templates), the facts behind it, and
where in the product the answer is to be looked at or given."""
from __future__ import annotations

from ontology_poc_generator.object_rows import _display, _labeller
from ontology_poc_generator.ontology_confirm import without_wrong
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal, normalize_value

MAX_MERGED = 3      # groups of an answer listed; the rest is in the check pack
MAX_SAME_NAME = 5   # groups of one type listed; all of them are counted
MAX_IDS = 5
SHARED_NAME_SHARE = 10   # a name field is the objects' own when no more than 1 in this many named objects shares a name
MAX_EXAMPLES = 3
UNANSWERED = ('query_limit', 'ontology_gap')


def _num(value) -> str:
    """Thousands separators and two decimals at most: 4176392.96 -> 4,176,392.96, 1308.0 -> 1,308."""
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
        if item['status'] != 'answered' or (place == 'acceptance' and item.get('note')):
            continue   # a person who wrote the basis down has already settled what the question means
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
                             [f'{_num(g["starts"])} 个{g["start"]}落在“{g["group"]}”这一组里'], question=question))
    return out


def _elsewhere(questions: dict, label) -> list:
    out = []
    for question, (item, place) in questions.items():
        found = _found_elsewhere(item) if item['status'] == 'no_data' else []
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
                         _qa_target(place, question), facts, question=question))
    return out


def _unlinked(fit: dict, types: dict, relations: dict, kept: dict, label, relation_name) -> list:
    orphans = {o['type']: o for o in fit.get('orphans') or []}
    out = []
    for stat in fit.get('relations') or []:
        left = stat['rows'] - stat['linked_rows']
        if left <= 0 or stat['key'] not in kept['relations']:
            continue
        r = relations[stat['key']]
        owner = next((k for k in (r['from'], r['to'], *types)
                      if any(pop['source'] == stat['source'] for pop in types[k]['populated_from'])), None)
        table = f'{label(owner)}（{stat["source"]}）' if owner else f'{stat["source"]} '
        other = r['from'] if owner == r['to'] else r['to']
        ask = (f'{table}{_num(stat["rows"])} 行里有 {_num(left)} 行没连上“{relation_name(r)}”。'
               f'是这些行本来就没有对应的{label(other)}，还是数据没导全？')
        examples = (orphans.get(r['from']) or {}).get('examples')
        facts = [*([f'没连上任何对象的{label(r["from"])}，例如 {"、".join(examples)}'] if examples else []),
                 *([f'其中 {_num(stat["empty_rows"])} 行用来连的编号是空的'] if stat.get('empty_rows') else [])]
        out.append(_item('unlinked', ask, {'tab': 'graph', 'relation': r['key']}, facts, relation=r['key']))
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
                         [f'{g[0][0]}：{numbers(g)}' for g in same[:MAX_SAME_NAME]]))
    return out


def _unstable(stability: dict, relations: dict, kept: dict, label, relation_name) -> list:
    runs = stability.get('runs')
    target = {'tab': 'objects', 'place': 'stability'}
    out = []
    for key, seen in (stability.get('relations') or {}).items():
        if seen < runs and key in kept['relations']:
            out.append(_item('unstable', f'关系“{relation_name(relations[key])}”在 {runs} 次建模里只出现了 {seen} 次。这条关系要保留吗？',
                             target, [f'共建模 {runs} 次，这条关系出现了 {seen} 次'], relation=key))
    for key, seen in (stability.get('types') or {}).items():
        if seen < runs and key in kept['types']:
            out.append(_item('unstable', f'对象“{label(key)}”在 {runs} 次建模里只出现了 {seen} 次。这类对象要保留吗？',
                             target, [f'共建模 {runs} 次，这类对象出现了 {seen} 次']))
    elsewhere = stability.get('elsewhere') or {}
    for kind, word in (('relations', '关系'), ('types', '对象')):
        for found in elsewhere.get(kind) or []:
            out.append(_item('unstable', f'另外 {found["count"]} 次建模里出现过{word}“{found["label"]}”，这次的本体里没有。要不要加？',
                             target, [f'共建模 {runs} 次，另外 {found["count"]} 次出现了它']))
    return out


def _check_findings(fit: dict, kept: dict, label, relations: dict) -> list:
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
                 and ('relation' not in x or x['relation'] in kept['relations'])]
        if found:
            lines = [line(x) for x in found[:MAX_EXAMPLES]]
            out.append(_item('check_finding', f'有 {_num(count(found))} {said}，例如{lines[0]}。{question}', {'tab': 'check'}, lines))
    return out


def _data_gaps(ontology: dict) -> list:
    gaps = ontology.get('data_gaps') or []
    return [_item('data_gaps', f'模型指出 {_num(len(gaps))} 处数据缺口（下面逐条）。客户那边有没有能补上的数据？',
                  {'tab': 'objects', 'place': 'build'}, gaps, from_model=True)] if gaps else []


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
                  {'tab': 'qa', 'place': 'ask'}, facts, from_model)]


def _unjudged(run: dict, p: dict) -> list:
    decisions = (run.get('confirmation') or {}).get('decisions') or {}
    objects = [t for t in p['object_types'] if not (decisions.get('types') or {}).get(t['key'], {}).get('verdict')]
    links = [r for r in p['relations'] if not (decisions.get('relations') or {}).get(r['key'], {}).get('verdict')]
    said = '、'.join(part for part in (f'{_num(len(objects))} 个对象' if objects else '', f'{_num(len(links))} 条关系' if links else '') if part)
    return [_item('unjudged', f'{said}还没人判过对错。会上逐项过一遍？', {'tab': 'objects', 'place': 'confirm'})] if said else []


def open_items(run: dict, bundle: dict, graph: dict | None = None) -> list:
    """The items for a kept table run, in the fixed order of their kinds (within a kind, in the order the data gives
    them). A run whose ontology did not pass verification has nothing to settle yet. `graph` is the run's own graph
    when the caller already holds it."""
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
    return [*_model_filters(questions, asked, label), *_merged(questions), *_elsewhere(questions, label),
            *_unlinked(fit, types, relations, kept, label, relation_name),
            *_same_name(p, bundle, graph or build_graph(ontology, bundle), kept, label),
            *_unstable(evaluation.get('stability') or {}, relations, kept, label, relation_name),
            *_check_findings(fit, kept, label, relations), *_data_gaps(ontology),
            *_unanswered(questions), *_unjudged(run, p)]

"""Numbers the team has checked (核对过的数): the team's own yardstick for what OntoPoc computes.

A builder (or an admin) marks one number as checked: a board card that shows one number (a number card, or an OntoPoc Query card that works out one number), or
one of their own saved answers that is one number. They write the value the team trusts (by default the one shown) and where it came from ("finance report Oct",
"SQL by X"); code keeps it with who, when, what OntoPoc computed then, and the dataset and definition versions that number was read from. A trusted value that differs
from what OntoPoc computes is allowed: that is the point of a yardstick, and it shows as 不一致 from the start.

From then on, each time the card or the answer is shown (and in the summaries), code works it out again through the same path that shows it (dashboards.evaluate,
the Q&A engine), with no model, and says one of four things:
  same     一致    the number now is the trusted value
  moved    变了    it is no longer what OntoPoc computed at the check: from → to, with the dataset and definition versions that moved since
  refused  拒答    it is not worked out on confirmed definitions now (one needs another look, is gone, or the card is closed to the reader): with the plain reason
  differs  不一致  it is what OntoPoc computed at the check, and that was never the trusted value
Nothing changes the trusted value but a new check, which is kept beside the earlier ones (the latest is the check).

Who sees what: a viewer, and a builder who cannot read the card's number now (its type or a column it reads is kept from them), sees on a board card only the
mark and who checked it when (the trusted value, its source or what was computed could tell them about rows or columns they may not read). A check is held against a card only as the board is worked out with no filter picked and the default parameters, and never for a reader whose
rows a rule limits. A saved answer stays its asker's: only they record or read its check; the team's tally counts checks and names no question.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import traceback

from ontology_poc_generator.caliber import lines_of, root_reason
from ontology_poc_generator.dashboards import DashboardRefused, _found, _is_admin, _owns, evaluate
from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_types import _content, element_row, type_id
from ontology_poc_generator.workspace_store import current_dataset

MAX_NOTE = 120
TALLY_WORKED_OUT = 5   # the tally works out again only the latest checked answers: each one runs its query over all the rows it reads
STATUSES = ('same', 'moved', 'refused', 'differs')
ANSWERED = ('answered', 'no_data')


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def _builds(user: dict | None) -> bool:
    return user is None or user['role'] in ('builder', 'admin')


def _plain(value):
    """A number as it is shown: a whole one without '.0'."""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def _same(a, b) -> bool:
    """Two numbers are the same to the cent: a team writes 1,234.57 for an average OntoPoc works out as 1234.5678."""
    return abs(float(a) - float(b)) < 0.005


def _status(trusted, then, now) -> str:
    if now is None:
        return 'refused'
    if _same(now, trusted):
        return 'same'
    return 'differs' if _same(now, then) else 'moved'


def answer_number(result: dict) -> float | None:
    """The one number an answer (a question's, or an OntoPoc Query card's) works out: a total or a count (of a list: the count it lists); None for groups, a
    graph, a share, one object by its key or an unknown total."""
    answer = result.get('answer')
    if result.get('status') not in ANSWERED or not isinstance(answer, dict) or 'groups' in answer or 'graph' in answer or 'share' in answer or 'lookup' in answer:
        return None
    if 'measure' in answer:
        return answer['measure'].get('value')
    return answer.get('total')


def _limited(worked: dict) -> bool:
    """Whether a reader's rows of what the number reads are limited by a row rule: their number is not the team's."""
    result = worked.get('result') or {}
    return bool(result.get('rows_limited') or result.get('limited_by_rule'))


def _card_number(component: dict, worked: dict) -> tuple[float | None, str | None]:
    """(the number a card shows on confirmed definitions, None) or (None, why not)."""
    if worked['status'] != 'ok':
        return None, worked.get('message') or tr('现在算不出来', 'It cannot be computed now')
    result = worked['result']
    standing = result.get('standing') or {}
    if not standing.get('confirmed', False):
        return None, standing.get('why') or tr('；', '; ').join(standing.get('reasons') or []) or tr('用到的定义现在不是已确认的状态', 'A definition it uses is not confirmed now')
    value = answer_number(result) if component['chart']['kind'] == 'query' else result.get('value')
    if value is None:
        return None, tr('现在没有算出一个数', 'No single number is computed now')
    return value, None


def _card_reads(conn, component: dict, result: dict) -> tuple[dict, list[dict]]:
    """({dataset: version}, [{'id', 'name', 'version'}]): what a card's number was read from, as it is now."""
    if component['chart']['kind'] == 'query':
        return dict(result.get('datasets') or {}), [{'id': d['id'], 'name': d['name'], 'version': d['version']} for d in result.get('definitions') or []]
    ids = list(dict.fromkeys([type_id(component['query']['type']), *(l['id'] for l in result['standing']['lines'] if l.get('kind') != 'note')]))
    definitions, types = [], []
    for line in lines_of(conn, ids):
        row = element_row(conn, line['id'])
        if row is None:
            continue
        content = _content(row)
        definitions.append({'id': line['id'], 'name': line['name'], 'version': row['version']})
        types.append(component['query']['type'] if line['kind'] == 'type' else content.get('type'))
    datasets = {}
    for english in dict.fromkeys(t for t in types if t):
        row = element_row(conn, type_id(english))
        dataset = current_dataset(conn, _content(row)['dataset']) if row else None
        if dataset:
            datasets[dataset['name']] = dataset['version']
    return datasets, definitions


def _moved(conn, row: dict) -> list[dict]:
    """The dataset and definition versions the number was read from that are not the ones now."""
    out = []
    for name, version in row['datasets'].items():
        now = current_dataset(conn, name)
        if (now['version'] if now else None) != version:
            out.append({'kind': 'dataset', 'name': name, 'from': version, 'to': now['version'] if now else None})
    for d in row['definitions']:
        now = element_row(conn, d['id'])
        if (now['version'] if now else None) != d['version']:
            out.append({'kind': 'definition', 'name': d['name'], 'from': d['version'], 'to': now['version'] if now else None})
    return out


def _view(conn, row: dict, now, reason: str | None, full: bool) -> dict:
    """A check as a person reads it: the mark and who checked it when; for a builder also the numbers, the source, why it refuses and what moved."""
    status = _status(row['trusted'], row['computed'], now)
    seen = {'status': status, 'by': row['by_name'], 'at': row['at']}
    if not full:
        return seen
    return {**seen, 'trusted': _plain(row['trusted']), 'then': _plain(row['computed']), 'now': _plain(now) if now is not None else None, 'note': row['note'],
            'reason': reason if status == 'refused' else None, 'moved': _moved(conn, row)}


def _card_key(component: dict, spec: dict) -> str:
    """What a check on a card is about: the card as it is and, for a query card, the board's default values of the $names it reads (they live on the board, not on
    the card). A check is held only against a card with the same key: another default is another number, never the same one."""
    from ontology_poc_generator.dashboards import _defaults
    from ontology_poc_generator.ontopoc_query import param_names
    names = param_names(component['text']) if 'text' in component else []
    if not names:
        return json.dumps(component, sort_keys=True, ensure_ascii=False)
    defaults = _defaults(spec)
    return json.dumps({'card': component, 'params': {n: defaults.get(n) for n in names}}, sort_keys=True, ensure_ascii=False)


COLUMNS = 'id, dashboard_id, component_id, component_json, question_id, trusted, computed, note, by_user_id, by_name, at, datasets_json, definitions_json'


def _row(found) -> dict:
    keys = [c.strip() for c in COLUMNS.split(',')]
    row = dict(zip(keys, found))
    return {**row, 'datasets': json.loads(row.pop('datasets_json')), 'definitions': json.loads(row.pop('definitions_json'))}


def _summary(statuses: list[str], what: str, what_en: str) -> dict:
    counts = {s: statuses.count(s) for s in STATUSES}
    total = len(statuses)
    text = tr(f'{total} 个{what}核对过：{counts["same"]} 一致、{counts["moved"]} 变了、{counts["refused"]} 拒答、{counts["differs"]} 不一致',
              f'{total} checked {what_en}: {counts["same"]} match, {counts["moved"]} moved, {counts["refused"]} refused, {counts["differs"]} differ') if total else ''
    return {'total': total, **counts, 'text': text}


# --- recording ---------------------------------------------------------------------------------------------------------------------------------------------

def _note(raw) -> str:
    text = raw.strip() if isinstance(raw, str) else ''
    if not text or len(text) > MAX_NOTE or '\n' in text:
        raise DashboardRefused(tr(f'写一句来源（例如“财务 10 月报表”“小王写的 SQL”），一行，最多 {MAX_NOTE} 个字', f'Write where the number comes from (for example "finance report Oct", "SQL by X"), one line, at most {MAX_NOTE} characters'))
    return text


def _trusted(raw, shown):
    """The value the team trusts: what was typed (1,234 and 1234.5 read as numbers), or the number shown when nothing was."""
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return shown
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise DashboardRefused(tr('团队信任的数要写成数字', 'The value the team trusts must be a number'))
    try:
        value = float(raw.replace(',', '').replace('，', '').replace(' ', '')) if isinstance(raw, str) else float(raw)
    except ValueError:
        raise DashboardRefused(tr('团队信任的数要写成数字，例如 119810 或 119,810', 'The value the team trusts must be a number, for example 119810 or 119,810')) from None
    if not math.isfinite(value):
        raise DashboardRefused(tr('团队信任的数要写成数字', 'The value the team trusts must be a number'))
    return value


def _insert(conn, user: dict | None, where: dict, trusted, computed, note: str, datasets: dict, definitions: list[dict]) -> dict:
    row = {'dashboard_id': where.get('dashboard_id'), 'component_id': where.get('component_id'), 'component_json': where.get('component_json'), 'question_id': where.get('question_id'),
           'trusted': float(trusted), 'computed': float(computed), 'note': note, 'by_user_id': user['id'] if user else None,
           'by_name': user['display_name'] if user else tr('本机', 'local'), 'at': _now(), 'datasets': datasets, 'definitions': definitions}
    conn.execute(f'INSERT INTO checked_number({COLUMNS.replace("id, ", "", 1)}) VALUES ({", ".join("?" * 12)})',
                 (row['dashboard_id'], row['component_id'], row['component_json'], row['question_id'], row['trusted'], row['computed'], row['note'], row['by_user_id'], row['by_name'],
                  row['at'], json.dumps(datasets, ensure_ascii=False), json.dumps(definitions, ensure_ascii=False)))
    return row


def record(conn, user: dict | None, payload: dict) -> dict:
    """Record a check: {'board', 'component', 'value'?, 'note'} for a board card, {'question', 'value'?, 'note'} for one of the person's own saved answers. Returns
    the check as its builder reads it. A number that is not worked out on confirmed definitions now, or over rows a rule limits, is no yardstick and is refused."""
    if not _builds(user):
        raise DashboardRefused(tr('只有建设者和管理员能记下核对过的数', 'Only builders and admins can record a checked number'), 403)
    if payload.get('question') is not None:
        return _record_answer(conn, user, payload)
    board = _found(conn, user, payload.get('board'))
    component = next((c for c in board['spec']['components'] if c['id'] == payload.get('component')), None)
    if component is None:
        raise DashboardRefused(tr('看板上没有这个组件', 'There is no such component on the board'), 404)
    if component['chart']['kind'] not in ('number', 'query'):
        raise DashboardRefused(tr('这个组件不是一个数：只有指标卡，或者算出一个数的本体查询，能核对', 'This component is not one number: only a number card, or an ontology query that works out one number, can be checked'))
    note = _note(payload.get('note'))
    worked = evaluate(conn, user, {**board['spec'], 'components': [component]}, {}, None, _owns(user, board) or _is_admin(user))[0]
    shown, why = _card_number(component, worked)
    if worked['status'] == 'ok' and component['chart']['kind'] == 'query' and worked['result'].get('standing', {}).get('confirmed') and shown is None:
        raise DashboardRefused(tr('这个查询算出的不是一个数（是分组或占比），不能核对', 'This query does not work out one number (it gives groups or a share), so it cannot be checked'))
    if shown is None:
        raise DashboardRefused(tr(f'这个数现在不是按已确认的定义算出的，不能拿来核对：{why}', f'This number is not worked out on confirmed definitions now, so it cannot be checked: {why}'))
    if _limited(worked):
        raise DashboardRefused(tr('你只能读到其中一部分行（行规则），核对要在全部行上做', 'A row rule lets you read only some of the rows; a check is made over all of them'))
    trusted = _trusted(payload.get('value'), shown)
    datasets, definitions = _card_reads(conn, component, worked['result'])
    row = _insert(conn, user, {'dashboard_id': board['id'], 'component_id': component['id'], 'component_json': _card_key(component, board['spec'])},
                  trusted, shown, note, datasets, definitions)
    return _view(conn, row, shown, None, True)


# --- a board's checks --------------------------------------------------------------------------------------------------------------------------------------

def _latest(conn, column: str, value) -> dict:
    """{target: the latest check} for a board's components (column dashboard_id) or for one question (column question_id)."""
    target = 'component_id' if column == 'dashboard_id' else 'question_id'
    found = conn.execute(f'SELECT {COLUMNS} FROM checked_number WHERE id IN (SELECT MAX(id) FROM checked_number WHERE {column} = ? GROUP BY {target})', (value,)).fetchall()
    return {r[target]: r for r in map(_row, found)}


def on_board(conn, user: dict | None, board: dict, components: list[dict], as_shown: bool) -> tuple[list[dict], dict]:
    """The board's components, each that carries a check with 'check' added, and the line at the top. `as_shown` is whether the board was worked out with no filter
    picked and the default parameters: a check is held only against that. A card changed since its check, or a query card whose default parameter values changed,
    carries none (the check was about the card and the values as they were)."""
    checks = _latest(conn, 'dashboard_id', board['id'])
    spec = {c['id']: _card_key(c, board['spec']) for c in board['spec']['components']}
    live = {k: r for k, r in checks.items() if spec.get(k) == r['component_json']}
    if not as_shown:
        return components, {**_summary([], '数', 'numbers'), 'text': tr('筛选或参数不是默认值时，不对照核对过的数', 'With a filter picked or a parameter typed, the board is not held against its checked numbers') if live else ''}
    out, statuses = [], []
    for c in components:
        row = live.get(c['id'])
        if row is None or _limited(c):
            out.append(c)
            continue
        try:
            now, why = _card_number(next(x for x in board['spec']['components'] if x['id'] == c['id']), c)
            full = _builds(user) and c['status'] == 'ok'   # the numbers, the source and the reasons only to a builder who reads the card's number now: one kept from its type or a column gets the mark
            seen = _view(conn, row, now, why, full)
        except Exception:   # noqa: BLE001 — a check is beside the number: one that cannot be worked out leaves the card without a mark, never the board without its cards
            traceback.print_exc()
            out.append(c)
            continue
        statuses.append(seen['status'])
        out.append({**c, 'check': seen})
    return out, _summary(statuses, '数', 'numbers')


# --- a saved answer's check -------------------------------------------------------------------------------------------------------------------------------

def _rerun(conn, asker: dict | None, question_id: int, stored: dict, question: str) -> dict:
    """A saved answer worked out again by code, as its asker, from the query it kept (no model), through the same gate as showing it again (workspace_questions.reopen):
    refused, with the plain reason, when reopening it would withhold it (a type it read is no longer theirs, a column is kept from them since, a row rule changed),
    when a definition it stood on is not confirmed now, when its type or a view it read is no longer in the asker's scope, or when a row rule limits what it reads
    now. It is never run over other rows than it read."""
    from ontology_poc_generator.ontopoc_query import QueryError
    from ontology_poc_generator.workspace_questions import QaRefused, _run_compiled, reopen, scope
    if stored.get('status') not in ANSWERED:   # what the asker was told was no number (a check stopped it): there is nothing to hold against the team's number
        return {'status': 'refused', 'reason': tr('这条回答当时没有算出一个数（被检查拦下或没有算出来），不能对照', 'This answer did not end in a number (a check stopped it, or it was not worked out), so it is not held against anything')}
    try:
        shown = reopen(conn, asker, question_id)
    except QaRefused as exc:
        return {'status': 'refused', 'reason': str(exc)}
    if 'withheld' in shown:
        return {'status': 'refused', 'reason': shown['reason']}
    lines = lines_of(conn, [d['id'] for d in stored.get('definitions') or []])
    if any(not l['confirmed'] for l in lines):
        return {'status': 'refused', 'reason': root_reason(conn, lines)}
    sc = scope(conn, asker)
    query = stored.get('query')
    if not isinstance(query, dict) or query.get('start') not in sc['types']:
        return {'status': 'refused', 'reason': tr('这条回答用到的对象类型现在不在你的范围里', 'An object type this answer used is no longer in your scope')}
    views = tuple(d['name'] for d in stored.get('definitions') or [] if d.get('kind') == 'view')
    gone = [v for v in views if v not in sc['views']]
    if gone:   # without its view the query would read more rows than the answer did: it is refused, never run wider
        return {'status': 'refused', 'reason': tr(f'这条回答用到的视图{"、".join(f"「{v}」" for v in gone)}现在不在你的范围里（例如它用的列设成了不发送取值），没有重算',
                                                  f'The view{"s" if len(gone) > 1 else ""} {", ".join(f"{chr(34)}{v}{chr(34)}" for v in gone)} this answer used {"are" if len(gone) > 1 else "is"} no longer in your scope (for example a column it uses was set to not send values), so it was not worked out again')}
    try:
        result = _run_compiled(conn, asker, sc, query, question, views)
    except (QueryError, KeyError, TypeError, ValueError, AttributeError):
        return {'status': 'refused', 'reason': tr('这条回答保存的查询现在跑不了', 'The query this answer kept cannot be run now')}
    if result.get('limited_by_rule'):   # the rows a rule lets the asker read are not the rows the team's number is about
        return {'status': 'refused', 'reason': tr('行规则现在只让你读到其中一部分行，不对照团队的数', 'A row rule now lets you read only some of the rows, so this is not held against the team\'s number')}
    return result


def _answer_now(result: dict) -> tuple[float | None, str | None]:
    if result.get('status') not in ANSWERED:
        return None, result.get('reason') or tr('现在没有算出来', 'It is not worked out now')
    value = answer_number(result)
    return (value, None) if value is not None else (None, tr('现在没有算出一个数', 'No single number is worked out now'))


def _own_question(conn, user: dict | None, question_id) -> tuple:
    if not isinstance(question_id, int) or isinstance(question_id, bool):
        raise DashboardRefused(tr('没有这条问题', 'No such question'), 404)
    where, args = ('user_id = ?', (user['id'],)) if user else ('user_id IS NULL', ())
    found = conn.execute(f'SELECT id, question, answer_json FROM qa_question WHERE id = ? AND {where}', (question_id, *args)).fetchone()
    if found is None:   # another person's question is theirs alone: it is not there for anyone else
        raise DashboardRefused(tr('没有这条问题', 'No such question'), 404)
    return found[0], found[1], json.loads(found[2])


def _record_answer(conn, user: dict | None, payload: dict) -> dict:
    qid, question, stored = _own_question(conn, user, payload.get('question'))
    note = _note(payload.get('note'))
    result = _rerun(conn, user, qid, stored, question)
    shown, why = _answer_now(result)
    if shown is None:
        raise DashboardRefused(tr(f'这条回答现在不能核对：{why}', f'This answer cannot be checked now: {why}'))
    trusted = _trusted(payload.get('value'), shown)
    row = _insert(conn, user, {'question_id': qid}, trusted, shown, note, dict(result.get('datasets') or {}),
                  [{'id': d['id'], 'name': d['name'], 'version': d['version']} for d in result.get('definitions') or []])
    return _view(conn, row, shown, None, True)


def question_check(conn, user: dict | None, question_id: int) -> dict:
    """The check of one of this person's saved answers, worked out again now: {'check': … or None}."""
    if not _builds(user):
        raise DashboardRefused(tr('只有建设者和管理员能记下核对过的数', 'Only builders and admins can record a checked number'), 403)
    qid, question, stored = _own_question(conn, user, question_id)
    row = _latest(conn, 'question_id', qid).get(qid)
    if row is None:
        return {'check': None}
    now, why = _answer_now(_rerun(conn, user, qid, stored, question))
    return {'check': _view(conn, row, now, why, True)}


def answers_tally(conn) -> dict:
    """The latest TALLY_WORKED_OUT checked answers, each worked out again as its asker: the counts of the four marks and one line, which says when older checks were
    left out ('all' is how many answers carry a check). No question and no source: the tally names nobody's."""
    from ontology_poc_generator.accounts import get_user
    checks = _all_question_checks(conn)
    statuses = []
    for row in checks[-TALLY_WORKED_OUT:] if TALLY_WORKED_OUT else []:
        found = conn.execute('SELECT user_id, question, answer_json FROM qa_question WHERE id = ?', (row['question_id'],)).fetchone()
        if found is None:
            continue
        asker = get_user(conn, found[0]) if found[0] is not None else None
        now, _ = _answer_now(_rerun(conn, asker, row['question_id'], json.loads(found[2]), found[1])) if asker is not None or found[0] is None else (None, None)
        statuses.append(_status(row['trusted'], row['computed'], now))
    out = {**_summary(statuses, '回答', 'answers'), 'all': len(checks)}
    if len(checks) > len(statuses) and statuses:
        c = out
        out['text'] = tr(f'只重算了最近核对的 {len(statuses)} 个（共 {len(checks)} 个回答核对过）：{c["same"]} 一致、{c["moved"]} 变了、{c["refused"]} 拒答、{c["differs"]} 不一致',
                         f'Only the {len(statuses)} most recently checked of {len(checks)} checked answers were worked out again: {c["same"]} match, {c["moved"]} moved, {c["refused"]} refused, {c["differs"]} differ')
    return out


def _all_question_checks(conn) -> list[dict]:
    found = conn.execute(f'SELECT {COLUMNS} FROM checked_number WHERE id IN (SELECT MAX(id) FROM checked_number WHERE question_id IS NOT NULL GROUP BY question_id) ORDER BY id').fetchall()
    return [_row(r) for r in found]

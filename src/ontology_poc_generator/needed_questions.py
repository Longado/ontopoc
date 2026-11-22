"""Questions we need (要回答的问题): the team's own list of the questions it needs answered, each held against what it should give.

A builder writes a question and, when it is known, what it should give: a number, or that it must be refused. That expectation is proposed by one person and
confirmed by another while two-person confirmation is on, by a person signed in to the page (never with a token), like any definition; changing the question's
words or what it should give puts it back to proposed. Confirming keeps the version of every dataset and every definition as they were then.

A builder or an admin whom no type list, column rule or row rule limits runs the list: each question is asked 1 to MAX_REPEATS times through the same path a
person's question takes (workspace_questions.ask), as the runner, so the gate, the refusals and the labels are the real ones; the asks are the run's, not the
runner's, and are not kept among their questions. Each question then comes back as one of:
  passes          every ask gave the expected number (exactly, as the answer states it), or every ask was refused when a refusal is expected
  differs         an ask gave another number (or a number where a refusal was expected), and nothing it read moved since the expectation was confirmed
  refused         no ask gave a wrong number but at least one was refused: with the definitions that block it and who can confirm them; never "differs"
  no_expectation  nothing confirmed to hold it against: the answer is shown, for a person to check against the data and adopt
  needs_look      it would differ, but a dataset or a definition the answers read has another version than when the expectation was confirmed: the expectation
                  goes back for a person to confirm again, and it does not count as a failure
  not_run         the model could not be reached and the run stopped before this question
with "N of M gave the expected number" and each distinct answer, since one question that gives two numbers is a fault this list exists to catch.

Cost: at most MAX_QUESTIONS questions; a run makes at most (questions x asks) model calls, one independent call per ask (nothing is chained), and all runs together
make at most SUITE_LIMIT calls in any SUITE_HOURS hours: their own line, apart from the questions a person may ask an hour (ask_budget), which a run does not
touch. One run at a time; a token and a demo guest cannot start one. The results are stored once and shown to builders and admins whom nothing limits (a
limited one sees neither the list nor its results: they are answered over every row and every type). Viewers do not see the list.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import math

from ontology_poc_generator.accounts import transaction, two_person
from ontology_poc_generator.checked_numbers import ANSWERED, answer_number
from ontology_poc_generator.lang import tr
from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION
from ontology_poc_generator.workspace_questions import QaRefused, _clean_question, ask
from ontology_poc_generator.workspace_store import log_line, now_text

MAX_QUESTIONS = 30
MAX_REPEATS = 5
MAX_NOTE = 120
SUITE_LIMIT = 300   # model calls all runs together may make in any SUITE_HOURS hours
SUITE_HOURS = 24
STALE_RUN_HOURS = 2   # a run still marked running after this long was cut off (the service stopped): it no longer holds the list
DEFINITION_PREFIXES = ('objtype:', 'relation:', 'enum:', 'objview:', 'derived:')
OUTCOMES = ('passes', 'differs', 'refused', 'no_expectation', 'needs_look', 'not_run')
COLUMNS = ('id, question, expect_kind, expect_value, note, state, version, written_by, written_by_user_id, written_at, confirmed_by, confirmed_by_user_id, confirmed_at, '
           'self_confirmed, basis_json, look_json')


def _plain(value):
    """A number as it is shown: a whole one without '.0'."""
    return int(value) if isinstance(value, float) and value.is_integer() else value


def same_number(expected, got) -> bool:
    """Exact, on the number as the answer states it: no rounding, no tolerance."""
    return expected is not None and got is not None and float(expected) == float(got)


def _name(user: dict | None) -> str:
    return user['display_name'] if user else tr('本机', 'local')


def _uid(user: dict | None):
    return user['id'] if user else None


# --- who ------------------------------------------------------------------------------------------------------------------------------------------------

def _limited(conn, user: dict | None) -> bool:
    from ontology_poc_generator.auth_http import limited_anywhere   # here: the gate is not needed by the rest of this module
    return limited_anywhere(conn, user)


def _limited_text() -> str:
    return tr('你看到的行或对象类型受行规则、类型名单或列权限限制；“要回答的问题”是在全部行和全部对象类型上答的，所以不给你看，也不能由你来跑。请管理员来跑，或者请他取消限制。',
              'A row rule, a type list or a column rule limits what you see. Questions we need are answered over every row and every type, so the list is not shown to you and you cannot run it. '
              'Ask an admin to run it, or to lift the limit.')


def _reader(conn, user: dict | None) -> None:
    """A builder or an admin whom nothing limits; QaRefused 403 for anyone else, in words that say nothing of what the list holds."""
    if user is not None and user['role'] not in ('builder', 'admin'):
        raise QaRefused(tr('“要回答的问题”只给建设者和管理员', 'Questions we need are for builders and admins'), 403)
    if _limited(conn, user):
        raise QaRefused(_limited_text(), 403)


def _person(user: dict | None) -> None:
    """What a token may not do here, whoever called: write, confirm or run (the gate refuses it first, access.token_allows)."""
    if user is not None and user.get('token_id') is not None:
        raise QaRefused(tr('“要回答的问题”要由本人登录页面来写、确认和运行，令牌不能做。', 'Questions we need are written, confirmed and run by a person signed in to the page, not with a token.'), 403)


# --- reading ----------------------------------------------------------------------------------------------------------------------------------------------

def _row(found) -> dict:
    row = dict(zip([c.strip() for c in COLUMNS.split(',')], found))
    return {**row, 'basis': json.loads(row.pop('basis_json')) if row['basis_json'] else None, 'look': json.loads(row.pop('look_json')) if row['look_json'] else []}


def _rows(conn) -> list[dict]:
    return [_row(r) for r in conn.execute(f'SELECT {COLUMNS} FROM needed_question ORDER BY id')]


def _found(conn, payload: dict) -> dict:
    qid = payload.get('id')
    found = conn.execute(f'SELECT {COLUMNS} FROM needed_question WHERE id = ?', (qid,)).fetchone() if isinstance(qid, int) and not isinstance(qid, bool) else None
    if found is None:
        raise QaRefused(tr('没有这个问题', 'No such question'), 404)
    row = _row(found)
    if payload.get('version') != row['version']:
        raise QaRefused(tr('这个问题刚被别人改过：请刷新后再看', 'Someone changed this question just now. Reload and look again'), 409)
    return row


def _expect_of(row: dict) -> dict | None:
    if row['expect_kind'] == 'number':
        return {'kind': 'number', 'value': _plain(row['expect_value'])}
    return {'kind': 'refused'} if row['expect_kind'] == 'refused' else None


def _last_run(conn) -> dict | None:
    found = conn.execute("SELECT id, by_name, started_at, finished_at, status, repeats, planned, calls, model, prompt_version, note FROM needed_run "
                         "WHERE status != 'running' ORDER BY id DESC LIMIT 1").fetchone()
    if found is None:
        return None
    keys = ('id', 'by', 'at', 'finished_at', 'status', 'repeats', 'planned', 'calls', 'model', 'prompt_version', 'note')
    run = dict(zip(keys, found))
    return {**run, 'stale_prompt': run['prompt_version'] != QUESTION_PROMPT_VERSION}   # the question prompt changed since: the model may now read the questions otherwise


def _results(conn, run_id) -> dict:
    return {qid: {**json.loads(stored), 'question': text} for qid, text, stored in conn.execute('SELECT question_id, question, result_json FROM needed_result WHERE run_id = ?', (run_id,))}


def _view(row: dict, user: dict | None, result: dict | None) -> dict:
    out = {'id': row['id'], 'question': row['question'], 'version': row['version'], 'state': row['state'], 'expect': _expect_of(row), 'note': row['note'],
           'written_by': row['written_by'], 'written_at': row['written_at'], 'confirmed_by': row['confirmed_by'], 'confirmed_at': row['confirmed_at'],
           'self_confirmed': bool(row['self_confirmed']), 'look': row['look'], 'mine': user is not None and row['written_by_user_id'] == user['id'], 'result': None}
    if result is not None:
        asked = result.pop('question')
        out['result'] = {**result, 'reworded': asked != row['question']}   # asked before the question was worded as it is now
    return out


def _one(conn, user: dict | None, qid: int) -> dict:
    row = _row(conn.execute(f'SELECT {COLUMNS} FROM needed_question WHERE id = ?', (qid,)).fetchone())
    run = _last_run(conn)
    return _view(row, user, _results(conn, run['id']).get(qid) if run else None)


def _since(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec='seconds')


def _used(conn) -> int:
    """The model calls of the runs in the last SUITE_HOURS hours; one still running counts what it may make."""
    return conn.execute("SELECT COALESCE(SUM(CASE WHEN status = 'running' THEN planned ELSE calls END), 0) FROM needed_run WHERE started_at > ?", (_since(SUITE_HOURS),)).fetchone()[0]


def _budget(conn) -> dict:
    used = _used(conn)
    return {'calls': SUITE_LIMIT, 'hours': SUITE_HOURS, 'used': used, 'left': max(0, SUITE_LIMIT - used)}


def _running(conn) -> bool:
    return conn.execute("SELECT 1 FROM needed_run WHERE status = 'running' AND started_at > ?", (_since(STALE_RUN_HOURS),)).fetchone() is not None


def _why_not(conn, user: dict | None, model_ready: bool, count: int) -> str | None:
    """Why this person cannot start a run now (the smallest one, each question asked once), or None."""
    if user is not None and user.get('token_id') is not None:
        return tr('令牌不能跑：请登录页面来跑', 'A token cannot run it: sign in to the page')
    if user is not None and user.get('provider') == 'demo':
        return tr('演示的访客不能跑', 'A demo guest cannot run it')
    if not count:
        return tr('列表里还没有问题：先写一个', 'The list has no question yet. Write one first')
    if not model_ready:
        return tr('本机服务没有模型凭据，不能跑', 'This server has no model credentials, so it cannot run')
    if _running(conn):
        return tr('列表正在跑，跑完再来', 'The list is running now. Run it again once that is done')
    left = _budget(conn)['left']
    if left < count:
        return tr(f'运行的模型调用在 {SUITE_HOURS} 小时内还剩 {left} 次，问一遍要 {count} 次', f'Runs have {left} model calls left in {SUITE_HOURS} hours, and asking each question once takes {count}')
    return None


def listing(conn, user: dict | None, model_ready: bool) -> dict:
    """The list as a builder or an admin whom nothing limits reads it: each question with its expectation, its state and what it came back as in the last run;
    the limits, the runs' budget line, the last run, and whether this person may start one now and why not."""
    _reader(conn, user)
    rows = _rows(conn)
    run = _last_run(conn)
    results = _results(conn, run['id']) if run else {}
    why = _why_not(conn, user, model_ready, len(rows))
    return {'questions': [_view(r, user, results.get(r['id'])) for r in rows], 'limits': {'questions': MAX_QUESTIONS, 'repeats': MAX_REPEATS},
            'budget': _budget(conn), 'last_run': run, 'can_run': {'ok': why is None, 'why': why}, 'two_person': two_person(conn)['active']}


# --- writing ------------------------------------------------------------------------------------------------------------------------------------------------

def _number(raw) -> float:
    """What was typed: 1234, 1,234 or 1234.5 read as a number."""
    bad = QaRefused(tr('期望的数要写成数字，例如 119810 或 119,810', 'The expected number must be a number, for example 119810 or 119,810'))
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise bad
    try:
        value = float(raw.replace(',', '').replace('，', '').replace(' ', '')) if isinstance(raw, str) else float(raw)
    except ValueError:
        raise bad from None
    if not math.isfinite(value):
        raise bad
    return value


def _expect(raw) -> tuple[str | None, float | None]:
    """(kind, value) of what the question should give: (None, None) when nothing is known yet."""
    if raw is None:
        return None, None
    if isinstance(raw, dict) and raw.get('kind') == 'number':
        return 'number', _number(raw.get('value'))
    if isinstance(raw, dict) and raw.get('kind') == 'refused':
        return 'refused', None
    raise QaRefused(tr('期望要写成一个数（{"kind": "number", "value": 16}），或者必须拒答（{"kind": "refused"}）',
                       'What it should give is a number ({"kind": "number", "value": 16}) or that it must be refused ({"kind": "refused"})'))


def _note(raw) -> str | None:
    if raw is None:
        return None
    text = raw.strip() if isinstance(raw, str) else None
    if text is None or len(text) > MAX_NOTE or '\n' in text:
        raise QaRefused(tr(f'来源写一行，最多 {MAX_NOTE} 个字（例如“财务 10 月报表”）', f'Write the source on one line, at most {MAX_NOTE} characters (for example "finance report Oct")'))
    return text or None


def _not_twice(conn, question: str, but=None) -> None:
    if conn.execute('SELECT 1 FROM needed_question WHERE question = ? AND id IS NOT ?', (question, but)).fetchone():
        raise QaRefused(tr('这个问题已经在列表里了', 'This question is already in the list'))


def _log(conn, user: dict | None, qid: int, change: str, before=None, after=None) -> None:
    log_line(conn, _name(user), f'needed:{qid}', change, before=before, after=after, user_id=_uid(user))


def _logged(row: dict) -> dict:
    return {'question': row['question'], 'state': row['state'], 'expect': _expect_of(row), 'note': row['note'], 'version': row['version']}


def write(conn, user: dict | None, payload: dict) -> dict:
    """A new question on the list: {question, expect?, note?}. With an expectation it is proposed by this person; without, it waits for one."""
    _reader(conn, user)
    _person(user)
    question = _clean_question(payload.get('question'))
    kind, value = _expect(payload.get('expect'))
    note = _note(payload.get('note'))
    with transaction(conn):
        if conn.execute('SELECT COUNT(*) FROM needed_question').fetchone()[0] >= MAX_QUESTIONS:
            raise QaRefused(tr(f'列表最多 {MAX_QUESTIONS} 个问题：先删掉一个再加', f'The list holds at most {MAX_QUESTIONS} questions. Remove one first'))
        _not_twice(conn, question)
        cursor = conn.execute('INSERT INTO needed_question(question, expect_kind, expect_value, note, state, version, written_by, written_by_user_id, written_at) VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)',
                              (question, kind, value, note, 'proposed' if kind else 'none', _name(user), _uid(user), now_text()))
        qid = cursor.lastrowid
        _log(conn, user, qid, 'written', after={'question': question, 'expect': _expect_of({'expect_kind': kind, 'expect_value': value}), 'note': note})
    return _one(conn, user, qid)


def update(conn, user: dict | None, payload: dict) -> dict:
    """{id, version, question?, expect?, note?}: new words or a new expectation (null: none known) put it back to proposed, written by this person; a new source alone
    leaves it as it stands."""
    _reader(conn, user)
    _person(user)
    with transaction(conn):
        row = _found(conn, payload)
        question = _clean_question(payload['question']) if 'question' in payload else row['question']
        kind, value = _expect(payload['expect']) if 'expect' in payload else (row['expect_kind'], row['expect_value'])
        note = _note(payload['note']) if 'note' in payload else row['note']
        reworded = question != row['question'] or kind != row['expect_kind'] or (kind == 'number' and value != row['expect_value'])
        if not reworded and note == row['note']:
            return _one(conn, user, row['id'])
        if question != row['question']:
            _not_twice(conn, question, row['id'])
        if reworded:
            conn.execute('UPDATE needed_question SET question = ?, expect_kind = ?, expect_value = ?, note = ?, state = ?, version = version + 1, written_by = ?, written_by_user_id = ?, written_at = ?, '
                         'confirmed_by = NULL, confirmed_by_user_id = NULL, confirmed_at = NULL, self_confirmed = 0, basis_json = NULL, look_json = NULL WHERE id = ?',
                         (question, kind, value, note, 'proposed' if kind else 'none', _name(user), _uid(user), now_text(), row['id']))
        else:
            conn.execute('UPDATE needed_question SET note = ?, version = version + 1 WHERE id = ?', (note, row['id']))
        after = _row(conn.execute(f'SELECT {COLUMNS} FROM needed_question WHERE id = ?', (row['id'],)).fetchone())
        _log(conn, user, row['id'], 'changed', before=_logged(row), after=_logged(after))
    return _one(conn, user, row['id'])


def delete(conn, user: dict | None, payload: dict) -> dict:
    """{id, version}: the question goes from the list (its past results with it)."""
    _reader(conn, user)
    _person(user)
    with transaction(conn):
        row = _found(conn, payload)
        conn.execute('DELETE FROM needed_question WHERE id = ?', (row['id'],))
        conn.execute('DELETE FROM needed_result WHERE question_id = ?', (row['id'],))
        _log(conn, user, row['id'], 'deleted', before=_logged(row))
    return {'ok': True}


def _basis(conn) -> dict:
    """What an expectation is confirmed on: the version of every current dataset and of every definition, as they are now."""
    datasets = {name: version for name, version in conn.execute('SELECT c.name, d.version FROM current_dataset c JOIN dataset d ON d.id = c.dataset_id')}
    like = ' OR '.join('element_id LIKE ?' for _ in DEFINITION_PREFIXES)
    definitions = {e: v for e, v in conn.execute(f'SELECT element_id, version FROM element_state WHERE {like}', [p + '%' for p in DEFINITION_PREFIXES])}
    return {'datasets': datasets, 'definitions': definitions}


def confirm(conn, user: dict | None, payload: dict) -> dict:
    """{id, version}: confirm what the question should give. While two-person confirmation is on, not by the person who wrote it. A person signed in to the page
    only (access.PERSON_ONLY_POSTS): "confirmed by" carries their name."""
    _reader(conn, user)
    _person(user)
    with transaction(conn):
        row = _found(conn, payload)
        if row['state'] == 'none':
            raise QaRefused(tr('先写它应该给出什么（一个数，或者必须拒答），再确认', 'First write what it should give (a number, or that it must be refused), then confirm it'))
        if row['state'] == 'confirmed':
            raise QaRefused(tr('这个期望已经确认了', 'This expectation is already confirmed'))
        own = user is not None and row['written_by_user_id'] is not None and row['written_by_user_id'] == user['id']
        if own and two_person(conn)['active']:
            raise QaRefused(tr('这一条是你自己提的，要另一位来确认', 'You put this forward yourself, so someone else must confirm it'), 403)
        conn.execute("UPDATE needed_question SET state = 'confirmed', version = version + 1, confirmed_by = ?, confirmed_by_user_id = ?, confirmed_at = ?, self_confirmed = ?, "
                     'basis_json = ?, look_json = NULL WHERE id = ?', (_name(user), _uid(user), now_text(), int(own), json.dumps(_basis(conn), ensure_ascii=False), row['id']))
        _log(conn, user, row['id'], 'confirmed', before=_logged(row), after={**_logged({**row, 'state': 'confirmed'}), **({'self_confirmed': True} if own else {})})
    return _one(conn, user, row['id'])


# --- running ------------------------------------------------------------------------------------------------------------------------------------------------

class _RunGateway:
    """The service's model, for one run: each call is counted, and its line in the model call log is marked as this run's."""

    def __init__(self, gateway, run_id: int):
        self._gateway, self.run_id, self.calls = gateway, run_id, 0

    @property
    def model(self):
        return getattr(self._gateway, 'model', None)

    def complete_json(self, **request):
        self.calls += 1
        return self._gateway.complete_json(**request)

    def log_call(self, record: dict) -> None:
        log = getattr(self._gateway, 'log_call', None)
        if log:
            log({**record, 'suite': True, 'run': self.run_id})


def _repeats(raw) -> int:
    if raw is None:
        return 1
    if isinstance(raw, bool) or not isinstance(raw, int) or not 1 <= raw <= MAX_REPEATS:
        raise QaRefused(tr(f'每个问题问 1 到 {MAX_REPEATS} 次', f'Each question is asked 1 to {MAX_REPEATS} times'))
    return raw


def _start(conn, user: dict | None, repeats: int, count: int) -> int:
    """The run's row, written only when no other run is going and the runs' budget has room for every call this one may make."""
    planned = count * repeats
    with transaction(conn):
        conn.execute("UPDATE needed_run SET status = 'stopped', finished_at = ?, note = ? WHERE status = 'running' AND started_at <= ?",
                     (now_text(), tr('这次运行没有跑完（服务停了）', 'This run did not finish (the service stopped)'), _since(STALE_RUN_HOURS)))
        if _running(conn):
            raise QaRefused(tr('列表正在跑，跑完再来', 'The list is running now. Run it again once that is done'), 409)
        used = _used(conn)
        if used + planned > SUITE_LIMIT:
            raise QaRefused(tr(f'运行的模型调用在任意 {SUITE_HOURS} 小时内最多 {SUITE_LIMIT} 次：已经用了 {used} 次，还剩 {max(0, SUITE_LIMIT - used)} 次，这次最多要 {planned} 次'
                               f'（{count} 个问题，每个问 {repeats} 次）。少问几次，或者晚些再跑。',
                               f'Runs may make {SUITE_LIMIT} model calls in any {SUITE_HOURS} hours. {used} are used, so {max(0, SUITE_LIMIT - used)} are left, and this run could make {planned} '
                               f'({count} questions, each asked {repeats} {"time" if repeats == 1 else "times"}). Ask fewer times, or run it later.'), 429)
        cursor = conn.execute("INSERT INTO needed_run(by_name, by_user_id, started_at, status, repeats, planned, calls, prompt_version) VALUES (?, ?, ?, 'running', ?, ?, 0, ?)",
                              (_name(user), _uid(user), now_text(), repeats, planned, QUESTION_PROMPT_VERSION))
        return cursor.lastrowid


def _ask_said(result: dict) -> dict:
    """What one ask came back as, kept with the run: the number, or the refusal with the definitions that block it and who can confirm them; and what it read."""
    answered = result['status'] in ANSWERED
    refusal = result.get('refusal') or {}
    blocking = [{k: d.get(k) for k in ('id', 'kind', 'name', 'state', 'who_can_confirm', 'text')} for d in refusal.get('definitions', []) if isinstance(d, dict) and d.get('id')] \
        if refusal.get('kind') in ('unsettled', 'unwalkable') else []
    return {'status': result['status'], 'number': _plain(answer_number(result)) if answered else None, 'reason': None if answered else result.get('reason'),
            'blocking': blocking, 'query_text': result.get('query_text'), 'datasets': dict(result.get('datasets') or {}),
            'definitions': [{'id': d['id'], 'name': d['name'], 'version': d['version']} for d in result.get('definitions') or []], 'model': result.get('model')}


def _moved(conn, basis: dict | None, asks: list[dict]) -> list[dict]:
    """What the answers read that has another version than when the expectation was confirmed: datasets, definitions they stood on, definitions a refusal named."""
    if not basis:
        return []
    out, seen = [], set()
    for a in asks:
        for name, version in a['datasets'].items():
            then = basis['datasets'].get(name)
            if then != version and ('dataset', name) not in seen:
                seen.add(('dataset', name))
                out.append({'kind': 'dataset', 'name': name, 'from': then, 'to': version})
        read = [(d['id'], d['name'], d['version']) for d in a['definitions']]
        read += [(b['id'], b['name'], (conn.execute('SELECT version FROM element_state WHERE element_id = ?', (b['id'],)).fetchone() or (None,))[0]) for b in a['blocking']]
        for element_id, name, version in read:
            then = basis['definitions'].get(element_id)
            if then != version and ('definition', element_id) not in seen:
                seen.add(('definition', element_id))
                out.append({'kind': 'definition', 'name': name, 'from': then, 'to': version})
    return out


def _distinct(asks: list[dict]) -> list[dict]:
    out = {}
    for a in asks:
        key = ('number', a['number']) if a['number'] is not None else ('status', a['status'])
        out.setdefault(key, {'number': a['number'], 'status': a['status'], 'times': 0})['times'] += 1
    return list(out.values())


def judge(conn, row: dict, asks: list[dict]) -> dict:
    """One question's outcome in a run, from its asks and its expectation as it stood when the run began."""
    expect = _expect_of(row) if row['state'] == 'confirmed' else None
    first = asks[0]
    out = {'outcome': None, 'asked': len(asks), 'right': None, 'distinct': _distinct(asks), 'expected': expect}
    if expect is None:
        return {**out, 'outcome': 'no_expectation', 'answer': {k: first[k] for k in ('status', 'number', 'reason', 'query_text')}, 'blocking': first['blocking']}
    refusals = [a for a in asks if a['status'] not in ANSWERED]
    if expect['kind'] == 'refused':
        right = len(refusals)
    else:
        right = sum(1 for a in asks if same_number(expect['value'], a['number']))
    wrong = len(asks) - right - (0 if expect['kind'] == 'refused' else len(refusals))
    out['right'] = right
    if not wrong and right == len(asks):
        return {**out, 'outcome': 'passes'}
    if not wrong:   # only refusals beside the right answers: refused, with what blocks it; never "differs"
        said = refusals[0]
        return {**out, 'outcome': 'refused', 'reason': said['reason'], 'blocking': said['blocking']}
    moved = _moved(conn, row['basis'], asks)
    return {**out, 'outcome': 'needs_look' if moved else 'differs', 'moved': moved}


def run(conn, gateway, user: dict | None, payload: dict) -> dict:
    """{repeats?}: ask every question on the list 1 to MAX_REPEATS times (default 1) as this person, through workspace_questions.ask without keeping the asks as
    theirs, and store what each came back as. Refused (403) to anyone but a builder or an admin whom nothing limits, to a token and to a demo guest; 400 for an
    empty list, 503 without a model, 409 while another run goes, 429 when the runs' budget has no room for every call this one may make. A model that cannot be
    reached stops the run: the questions not asked come back as not run. Returns the list as listing() reads it."""
    if user is not None and user['role'] not in ('builder', 'admin'):
        raise QaRefused(tr('“要回答的问题”只给建设者和管理员', 'Questions we need are for builders and admins'), 403)
    _person(user)
    if user is not None and user.get('provider') == 'demo':
        raise QaRefused(tr('演示的访客不能跑“要回答的问题”', 'A demo guest cannot run Questions we need'), 403)
    _reader(conn, user)
    repeats = _repeats(payload.get('repeats'))
    rows = _rows(conn)
    if not rows:
        raise QaRefused(tr('列表里还没有问题：先写一个', 'The list has no question yet. Write one first'))
    if gateway is None:
        raise QaRefused(tr('本机服务没有模型凭据：设置 DEEPSEEK_API_KEY 或 OPENROUTER_API_KEY 后重启 ontology_server，再来跑。',
                           'This server has no model credentials. Set DEEPSEEK_API_KEY or OPENROUTER_API_KEY and restart ontology_server, then run it.'), 503)
    run_id = _start(conn, user, repeats, len(rows))
    counted = _RunGateway(gateway, run_id)
    judged, stopped, model = {}, None, None
    try:
        for row in rows:
            asks = []
            for _ in range(repeats if stopped is None else 0):
                try:
                    said = _ask_said(ask(conn, counted, user, row['question'], keep=False))
                except QaRefused as exc:
                    if exc.status in (502, 503):   # the model could not be reached: nothing more is asked
                        stopped = str(exc)
                        break
                    said = {'status': 'refused', 'number': None, 'reason': str(exc), 'blocking': [], 'query_text': None, 'datasets': {}, 'definitions': [], 'model': None}
                model = model or said['model']
                asks.append(said)
            if stopped is not None:
                judged[row['id']] = (row, {'outcome': 'not_run', 'asked': 0, 'right': None, 'distinct': [], 'expected': _expect_of(row) if row['state'] == 'confirmed' else None})
            else:
                judged[row['id']] = (row, judge(conn, row, asks))
    except BaseException:   # whatever stopped it, the run is closed with what it asked, so the list is not left running
        _finish(conn, user, run_id, counted.calls, model, stopped or tr('这次运行出错停了，详情见服务日志', 'This run stopped on an error; see the service log'), judged)
        raise
    _finish(conn, user, run_id, counted.calls, model, stopped, judged)
    return listing(conn, user, True)


def _finish(conn, user: dict | None, run_id: int, calls: int, model, stopped, judged: dict) -> None:
    """Store the run once: what each question came back as, and every expectation that needs another look goes back for a person (unless it was changed meanwhile)."""
    with transaction(conn):
        for qid, (row, result) in judged.items():
            conn.execute('INSERT INTO needed_result(run_id, question_id, question, outcome, result_json) VALUES (?, ?, ?, ?, ?)',
                         (run_id, qid, row['question'], result['outcome'], json.dumps(result, ensure_ascii=False)))
            if result['outcome'] == 'needs_look':
                changed = conn.execute("UPDATE needed_question SET state = 'needs_look', version = version + 1, look_json = ? WHERE id = ? AND version = ? AND state = 'confirmed'",
                                       (json.dumps(result['moved'], ensure_ascii=False), qid, row['version'])).rowcount
                if changed:
                    _log(conn, user, qid, 'needs_look', before=_logged(row), after={'state': 'needs_look', 'moved': result['moved'], 'run': run_id})
        conn.execute('UPDATE needed_run SET status = ?, finished_at = ?, calls = ?, model = ?, note = ? WHERE id = ?',
                     ('stopped' if stopped is not None else 'done', now_text(), calls, model, stopped, run_id))
        log_line(conn, _name(user), f'needed-run:{run_id}', 'run', after={'calls': calls, 'questions': len(judged), 'stopped': stopped is not None}, user_id=_uid(user))

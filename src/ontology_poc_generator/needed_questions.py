"""Questions we need (要回答的问题): the team's own list of the questions it needs answered, each held against what it should give.

A builder writes a question and, when it is known, what it should give: a number, or that it must be refused (optionally: refused because of one named
definition). That expectation is proposed by one person and confirmed by another while two-person confirmation is on, by a person signed in to the page (never
with a token), like any definition; changing the question's words or what it should give puts it back to proposed.

What an expectation stands on is what the expected answer read: the datasets and definitions, at their versions, that an answer giving the expected result used
(answer['datasets'], answer['definitions'], and for a refusal the definitions that blocked it). It is taken at confirmation from the last run's asks of the
question that gave the expected result, and taken again each time a run passes; with neither, nothing is recorded and a wrong result is a failure.

A builder or an admin whom no type list, column rule or row rule limits runs the list: each question is asked 1 to MAX_REPEATS times through the same path a
person's question takes (workspace_questions.ask), as the runner, so the gate, the refusals and the labels are the real ones; the asks are the run's, not the
runner's, and are not kept among their questions. An ask ends as a number (or another answer), as a refusal the gate made (GATE: a definition not confirmed or
waiting, nothing in scope, a relation that cannot be followed, a query that left out a confirmed definition, a measure waiting for confirming), or with no answer
(a reply that could not be read, the model saying the question is outside what it knows, a query it could not write or run). Each question then comes back as:
  passes          every ask gave the expected number (exactly, as the answer states it), or every ask was a refusal the gate made (naming the expected
                  definition, when one is named)
  differs         an ask gave another number, or an answer where a refusal was expected, and nothing the expected answer read has moved: a failure
  needs_look      the same, but a dataset or definition the expected answer read has another version now: the expectation goes back for a person to confirm
                  again, and it does not count as a failure
  refused         no wrong answer, but the gate refused at least one ask (not the way the expectation says, if it expects a refusal): with what blocks it and
                  who can confirm it; never "differs"
  no_answer       no ask gave an answer or a refusal of the gate: never a pass and never a refusal
  no_expectation  nothing confirmed to hold it against: every answer is shown, for a person to check against the data and adopt
  not_run         the run stopped (the model could not be reached, or an error) before this question
A result belongs to the expectation it was judged against (its words, its expectation and expect_version, which counts each new expectation and each
confirmation). Once the question is worded otherwise, its expectation changes or it is confirmed again, the earlier result is shown only as what was answered
then (not_run_since_change), never with its verdict, until the next run judges it again.
with "N of M gave the expected number" and each distinct answer, since one question that gives two numbers is a fault this list exists to catch; and, when the
answers now read other definitions than the expected answer did, which.

Cost: at most MAX_QUESTIONS questions; a run makes at most (questions x asks) model calls, one independent call per ask (nothing is chained), and all runs together
make at most SUITE_LIMIT calls in any SUITE_HOURS hours: their own line, apart from the questions a person may ask an hour (ask_budget), which a run does not
touch. Each call is charged as it goes out. A run goes on in the service after the request that starts it (start); one run at a time; one the service lost
(it stopped) is closed as stopped on the next request, with the calls it made charged. A token and a demo guest cannot start one. The results are stored once
and shown to builders and admins whom nothing limits (a limited one sees neither the list nor its results: they are answered over every row and every type).
Viewers do not see the list.
"""
from __future__ import annotations

import contextvars
from datetime import datetime, timedelta, timezone
import json
import math
import re
import threading
import traceback
import uuid

from ontology_poc_generator.accounts import transaction, two_person
from ontology_poc_generator.checked_numbers import ANSWERED, answer_number
from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_types import element_row
from ontology_poc_generator.ontology_questions import QUESTION_PROMPT_VERSION
from ontology_poc_generator.workspace_questions import HELD_BACK as GATE, QaRefused, _clean_question, ask
from ontology_poc_generator.workspace_store import current_dataset, fingerprint, log_line, now_text, writers_in_log

MAX_QUESTIONS = 30
MAX_REPEATS = 5
MAX_NOTE = 120
SUITE_LIMIT = 300   # model calls all runs together may make in any SUITE_HOURS hours
SUITE_HOURS = 24
OUTCOMES = ('passes', 'differs', 'needs_look', 'refused', 'no_answer', 'no_expectation', 'not_run')   # and, shown only: not_run_since_change
DEFINITION_PREFIXES = ('objtype:', 'relation:', 'enum:', 'objview:', 'derived:')
COLUMNS = ('id, question, expect_kind, expect_value, expect_blocker, expect_version, note, state, version, written_by, written_by_user_id, written_at, confirmed_by, confirmed_by_user_id, '
           'confirmed_at, self_confirmed, basis_json, look_json, changed_json')
_LIVE: set[str] = set()   # the runs this service is running now, by the token written on their row: a running row with another token was cut off
_LIVE_LOCK = threading.Lock()


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


# --- who changed it since it was last confirmed ----------------------------------------------------------------------------------------------------------
# The rule of the team's definitions (workspace_store.may_confirm), kept for an expectation in needed_question.changed_json: {"by": the accounts that changed what
# it should give (its words, the number or the refusal it expects) since it was last confirmed or written, "of": a fingerprint of what the record describes,
# "confirmed": what was last confirmed, "was": the confirmed state an edit sent back}. Its source (the note) is not what is confirmed: changing it alone keeps the
# state, as before.

def _content(row: dict) -> str:
    """What a person confirms of an expectation: its words and what it should give."""
    return json.dumps([row['question'], row['expect_kind'], row['expect_value'] if row['expect_kind'] == 'number' else None, row['expect_blocker']], ensure_ascii=False)


def _kept(row: dict) -> dict | None:
    kept = json.loads(row['changed_json']) if row.get('changed_json') else None
    return kept if kept is not None and kept.get('of') == fingerprint(_content(row)) else None


def _changers(conn, row: dict) -> set[int]:
    """Who changed it since it was last confirmed; without a record that describes it as it stands, everyone the log names since then (and whoever the record names)."""
    kept = _kept(row)
    if kept is not None:
        return set(kept.get('by') or [])
    stale = json.loads(row['changed_json']) if row.get('changed_json') else {}
    return set(stale.get('by') or []) | writers_in_log(conn, f'needed:{row["id"]}', ('written', 'changed'))


def _barred(conn, row: dict) -> set[int]:
    return _changers(conn, row) | ({row['written_by_user_id']} if row['written_by_user_id'] is not None else set())


def _held(conn, row: dict) -> str | None:
    """Who may not confirm it and the ways out, while two-person confirmation is active (object_types.held_note, for an expectation)."""
    held = _barred(conn, row)
    if not held - {row['written_by_user_id']} or not two_person(conn)['active']:   # only its writer: they read, as before, that someone else confirms what they wrote
        return None
    names = dict(conn.execute('SELECT id, display_name FROM user'))
    who = sorted((names.get(p, str(p)) for p in held))
    free = [n for i, n in conn.execute("SELECT id, display_name FROM user WHERE disabled = 0 AND role IN ('builder', 'admin') ORDER BY display_name") if i not in held]
    confirmed = (_kept(row) or {}).get('confirmed') is not None or row['state'] == 'needs_look'
    listed, one = tr('、', ', ').join(who), len(who) == 1
    said = (tr(f'{listed} 在上次确认之后改过它（或写了它），{"不能" if one else "都不能"}确认它', f'{listed} changed it since it was last confirmed (or wrote it), so they cannot confirm it') if confirmed
            else tr(f'{listed} 写过或改过它，还没有别人确认过，{"不能" if one else "都不能"}确认它', f'{listed} wrote or changed it and nobody else has confirmed it, so they cannot confirm it'))
    other = tr('另一位' if one else '第三位', 'someone else' if one else 'a third person')
    out = (tr(f'请没有改过它的{other}来确认（可以确认的人：{tr("、", ", ").join(free)}）', f'ask {other} who did not change it to confirm it (who can: {", ".join(free)})') if free
           else tr(f'请没有改过它的{other}来确认（现在没有这样的建设者，管理员可以加一位）', f'ask {other} who did not change it to confirm it (there is no such builder now; an admin can add one)'))
    if confirmed:
        out += tr('，或把它改回上次确认的样子', ', or put back what was last confirmed')
    return tr(f'{said}。出路：{out}。', f'{said}. The way out: {out}.')


# --- reading ----------------------------------------------------------------------------------------------------------------------------------------------

def _basis_of(stored) -> dict | None:
    """What an expectation stands on, as recorded: {'datasets': {name: version}, 'definitions': {id: {'name', 'version'}}}. A record of every dataset and every
    definition in the workspace (kept before what an answer read was recorded) says nothing of what the answer read: none."""
    if not isinstance(stored, dict) or not all(isinstance(d, dict) for d in (stored.get('definitions') or {}).values()):
        return None
    return stored


def _row(found) -> dict:
    row = dict(zip([c.strip() for c in COLUMNS.split(',')], found))
    return {**row, 'basis': _basis_of(json.loads(row.pop('basis_json')) if row['basis_json'] else None), 'look': json.loads(row.pop('look_json')) if row['look_json'] else []}


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
    if row['expect_kind'] == 'refused':
        return {'kind': 'refused', **({'blocker': row['expect_blocker']} if row.get('expect_blocker') else {})}
    return None


RUN_KEYS = ('id', 'by', 'at', 'finished_at', 'status', 'repeats', 'planned', 'calls', 'model', 'prompt_version', 'note')


def _last_run(conn) -> dict | None:
    found = conn.execute(f"SELECT {', '.join(k if k not in ('by', 'at') else {'by': 'by_name', 'at': 'started_at'}[k] for k in RUN_KEYS)} FROM needed_run "
                         "WHERE status != 'running' ORDER BY id DESC LIMIT 1").fetchone()
    if found is None:
        return None
    run = dict(zip(RUN_KEYS, found))
    return {**run, 'stale_prompt': run['prompt_version'] != QUESTION_PROMPT_VERSION}   # the question prompt changed since: the model may now read the questions otherwise


def _running_now(conn) -> dict | None:
    found = conn.execute("SELECT id, by_name, started_at, repeats, planned, calls FROM needed_run WHERE status = 'running' ORDER BY id DESC LIMIT 1").fetchone()
    return dict(zip(('id', 'by', 'at', 'repeats', 'planned', 'calls'), found)) if found else None


def _results(conn, run: dict | None) -> dict:
    if run is None:
        return {}
    return {qid: {**json.loads(stored), 'question': text, 'run_at': run['at']}
            for qid, text, stored in conn.execute('SELECT question_id, question, result_json FROM needed_result WHERE run_id = ?', (run['id'],))}


def _judged_against(row: dict) -> dict:
    return {'question': row['question'], 'expect_version': row['expect_version'], 'expect': _expect_of(row) if row['state'] == 'confirmed' else None}


def _shown(row: dict, result: dict) -> dict:
    """A stored result as the question shows it now: its verdict while the question stands as it was judged (same words, same expectation, not confirmed again
    since); otherwise only what was answered then, and when."""
    then = result.get('judged_against') or {}
    if then.get('question') == row['question'] and then.get('expect_version') == row['expect_version'] and result['question'] == row['question']:
        return {k: v for k, v in result.items() if k not in ('question', 'asks', 'run_at', 'judged_against')}   # each ask's record is kept for confirming, not shown
    return {'outcome': 'not_run_since_change', 'earlier': {'at': result['run_at'], 'question': result['question'], 'asked': result['asked'], 'distinct': result['distinct']}}


def _view(conn, row: dict, user: dict | None, result: dict | None) -> dict:
    out = {'id': row['id'], 'question': row['question'], 'version': row['version'], 'state': row['state'], 'expect': _expect_of(row), 'note': row['note'],
           'written_by': row['written_by'], 'written_at': row['written_at'], 'confirmed_by': row['confirmed_by'], 'confirmed_at': row['confirmed_at'],
           'self_confirmed': bool(row['self_confirmed']), 'look': row['look'], 'mine': user is not None and user['id'] in _barred(conn, row), 'result': None,
           'held': _held(conn, row) if row['state'] in ('proposed', 'needs_look') else None}   # who wrote or changed it since it was last confirmed, and the ways out
    if result is not None:
        out['result'] = _shown(row, result)
    return out


def _one(conn, user: dict | None, qid: int) -> dict:
    row = _row(conn.execute(f'SELECT {COLUMNS} FROM needed_question WHERE id = ?', (qid,)).fetchone())
    return _view(conn, row, user, _results(conn, _last_run(conn)).get(qid))


def _since(hours: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec='seconds')


def _close_cut_off(conn) -> None:
    """A run still marked running that this service is not running was cut off (the service stopped while it went): closed as stopped, its calls charged."""
    for run_id, owner in conn.execute("SELECT id, owner FROM needed_run WHERE status = 'running'").fetchall():
        with _LIVE_LOCK:
            live = owner in _LIVE
        if not live:
            conn.execute("UPDATE needed_run SET status = 'stopped', finished_at = ?, note = ? WHERE id = ? AND status = 'running'",
                         (now_text(), tr('这次运行没有跑完（服务停了），已经发出的调用照算', 'This run did not finish (the service stopped); the calls it made are charged'), run_id))


def _used(conn) -> int:
    """The model calls of the runs in the last SUITE_HOURS hours; the one running counts every call it may make."""
    return conn.execute("SELECT COALESCE(SUM(CASE WHEN status = 'running' THEN planned ELSE calls END), 0) FROM needed_run WHERE started_at > ?", (_since(SUITE_HOURS),)).fetchone()[0]


def _budget(conn) -> dict:
    used = _used(conn)
    return {'calls': SUITE_LIMIT, 'hours': SUITE_HOURS, 'used': used, 'left': max(0, SUITE_LIMIT - used)}


def _busy_text() -> str:
    return tr('列表正在跑，跑完再来', 'The list is running now. Run it again once that is done')


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
    if _running_now(conn):
        return _busy_text()
    left = _budget(conn)['left']
    if left < count:
        return tr(f'运行的模型调用在 {SUITE_HOURS} 小时内还剩 {left} 次，问一遍要 {count} 次', f'Runs have {left} model calls left in {SUITE_HOURS} hours, and asking each question once takes {count}')
    return None


def listing(conn, user: dict | None, model_ready: bool) -> dict:
    """The list as a builder or an admin whom nothing limits reads it: each question with its expectation, its state and what it came back as in the last run;
    the limits, the runs' budget line, the run going now and the last one, and whether this person may start one now and why not."""
    _reader(conn, user)
    _close_cut_off(conn)
    rows = _rows(conn)
    run = _last_run(conn)
    results = _results(conn, run)
    why = _why_not(conn, user, model_ready, len(rows))
    return {'questions': [_view(conn, r, user, results.get(r['id'])) for r in rows], 'limits': {'questions': MAX_QUESTIONS, 'repeats': MAX_REPEATS},
            'budget': _budget(conn), 'running': _running_now(conn), 'last_run': run, 'can_run': {'ok': why is None, 'why': why}, 'two_person': two_person(conn)['active']}


# --- writing ------------------------------------------------------------------------------------------------------------------------------------------------

_PLAIN_NUMBER = re.compile(r'[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?', re.ASCII)   # 1234, 1,234, 1234.5, 1,234.5: thousands with commas, a point for the fraction


def _number(raw) -> float:
    """What was typed, read only when it is plainly a number: 1234, 1,234, 1234.5 or 1,234.5 (a full-width comma counts as a comma). "1.234,5", "1,2,3" or
    "1 234" are refused rather than guessed."""
    bad = QaRefused(tr('期望的数要写成数字，例如 119810、119,810 或 1,234.5', 'The expected number must be a number, for example 119810, 119,810 or 1,234.5'))
    if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
        raise bad
    if isinstance(raw, str):
        text = raw.strip().replace('，', ',')
        if not _PLAIN_NUMBER.fullmatch(text):
            raise bad
        value = float(text.replace(',', ''))
    else:
        value = float(raw)
    if not math.isfinite(value):
        raise bad
    return value


def _blocker(raw) -> str | None:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return None
    text = raw.strip() if isinstance(raw, str) else None
    if text is None or len(text) > MAX_NOTE or '\n' in text:
        raise QaRefused(tr(f'挡住它的定义写名字，一行，最多 {MAX_NOTE} 个字', f'Name the definition that must block it on one line, at most {MAX_NOTE} characters'))
    return text


def _one_definition(conn, blocker: str) -> None:
    """A blocker written by name must name one definition: a name two share (a view and a type, say) is refused, with the ids that tell them apart."""
    from ontology_poc_generator.workspace_questions import _kind_and_name
    if element_row(conn, blocker) is not None:
        return
    like = ' OR '.join('element_id LIKE ?' for _ in DEFINITION_PREFIXES)
    ids = []
    for (element_id,) in conn.execute(f'SELECT element_id FROM element_state WHERE {like} ORDER BY element_id', [p + '%' for p in DEFINITION_PREFIXES]).fetchall():
        try:
            if _kind_and_name(conn, element_row(conn, element_id))[1] == blocker:
                ids.append(element_id)
        except (KeyError, TypeError):   # a meaning whose type is gone has no name to match
            continue
    if len(ids) > 1:
        raise QaRefused(tr(f'有 {len(ids)} 个定义都叫“{blocker}”：请写你指的那个的编号：{"、".join(ids)}', f'{len(ids)} definitions are called "{blocker}". Write the id of the one you mean: {", ".join(ids)}'))


def _expect(raw) -> tuple[str | None, float | None, str | None]:
    """(kind, value, blocker) of what the question should give: (None, None, None) when nothing is known yet."""
    if raw is None:
        return None, None, None
    if isinstance(raw, dict) and raw.get('kind') == 'number':
        return 'number', _number(raw.get('value')), None
    if isinstance(raw, dict) and raw.get('kind') == 'refused':
        return 'refused', None, _blocker(raw.get('blocker'))
    raise QaRefused(tr('期望要写成一个数（{"kind": "number", "value": 16}），或者必须拒答（{"kind": "refused"}，可以加上挡住它的定义 "blocker"）',
                       'What it should give is a number ({"kind": "number", "value": 16}) or that it must be refused ({"kind": "refused"}, with "blocker", the definition that must block it, if you like)'))


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
    kind, value, blocker = _expect(payload.get('expect'))
    note = _note(payload.get('note'))
    with transaction(conn):
        if conn.execute('SELECT COUNT(*) FROM needed_question').fetchone()[0] >= MAX_QUESTIONS:
            raise QaRefused(tr(f'列表最多 {MAX_QUESTIONS} 个问题：先删掉一个再加', f'The list holds at most {MAX_QUESTIONS} questions. Remove one first'))
        _not_twice(conn, question)
        if blocker is not None:
            _one_definition(conn, blocker)
        record = json.dumps({'by': [_uid(user)] if _uid(user) is not None else [], 'of': fingerprint(_content({'question': question, 'expect_kind': kind, 'expect_value': value, 'expect_blocker': blocker}))})
        cursor = conn.execute('INSERT INTO needed_question(question, expect_kind, expect_value, expect_blocker, note, state, version, written_by, written_by_user_id, written_at, changed_json) '
                              'VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)', (question, kind, value, blocker, note, 'proposed' if kind else 'none', _name(user), _uid(user), now_text(), record))
        qid = cursor.lastrowid
        _log(conn, user, qid, 'written', after={'question': question, 'expect': _expect_of({'expect_kind': kind, 'expect_value': value, 'expect_blocker': blocker}), 'note': note})
    return _one(conn, user, qid)


def update(conn, user: dict | None, payload: dict) -> dict:
    """{id, version, question?, expect?, note?}: new words or a new expectation (null: none known) put it back to proposed, written by this person; a new source alone
    leaves it as it stands."""
    _reader(conn, user)
    _person(user)
    with transaction(conn):
        row = _found(conn, payload)
        question = _clean_question(payload['question']) if 'question' in payload else row['question']
        kind, value, blocker = _expect(payload['expect']) if 'expect' in payload else (row['expect_kind'], row['expect_value'], row['expect_blocker'])
        note = _note(payload['note']) if 'note' in payload else row['note']
        reworded = (question, kind, value if kind == 'number' else None, blocker) != (row['question'], row['expect_kind'], row['expect_value'] if row['expect_kind'] == 'number' else None, row['expect_blocker'])
        if not reworded and note == row['note']:
            return _one(conn, user, row['id'])
        if question != row['question']:
            _not_twice(conn, question, row['id'])
        if blocker is not None and blocker != row['expect_blocker']:
            _one_definition(conn, blocker)
        back = False
        if reworded:
            record, was = _next_record(conn, row, {'question': question, 'expect_kind': kind, 'expect_value': value, 'expect_blocker': blocker}, _uid(user))
            if was is not None:   # what it should give is again what was last confirmed, and an edit is what sent it back: confirmed again as it was
                back = True
                conn.execute('UPDATE needed_question SET question = ?, expect_kind = ?, expect_value = ?, expect_blocker = ?, note = ?, state = ?, version = version + 1, expect_version = ?, '
                             'written_by = ?, written_by_user_id = ?, written_at = ?, confirmed_by = ?, confirmed_by_user_id = ?, confirmed_at = ?, self_confirmed = ?, basis_json = ?, look_json = ?, '
                             'changed_json = ? WHERE id = ?',
                             (question, kind, value, blocker, note, was['state'], was['expect_version'], was['written_by'], was['written_by_user_id'], was['written_at'], was['confirmed_by'],
                              was['confirmed_by_user_id'], was['confirmed_at'], was['self_confirmed'], was['basis_json'], was['look_json'], record, row['id']))
            else:
                conn.execute('UPDATE needed_question SET question = ?, expect_kind = ?, expect_value = ?, expect_blocker = ?, note = ?, state = ?, version = version + 1, '
                             'expect_version = expect_version + 1, written_by = ?, '
                             'written_by_user_id = ?, written_at = ?, confirmed_by = NULL, confirmed_by_user_id = NULL, confirmed_at = NULL, self_confirmed = 0, basis_json = NULL, look_json = NULL, '
                             'changed_json = ? WHERE id = ?',
                             (question, kind, value, blocker, note, 'proposed' if kind else 'none', _name(user), _uid(user), now_text(), record, row['id']))
        else:
            conn.execute('UPDATE needed_question SET note = ?, version = version + 1 WHERE id = ?', (note, row['id']))
        after = _row(conn.execute(f'SELECT {COLUMNS} FROM needed_question WHERE id = ?', (row['id'],)).fetchone())
        _log(conn, user, row['id'], 'restored' if back else 'changed', before=_logged(row), after=_logged(after))
    return _one(conn, user, row['id'])


_WAS = ('state', 'expect_version', 'written_by', 'written_by_user_id', 'written_at', 'confirmed_by', 'confirmed_by_user_id', 'confirmed_at', 'self_confirmed', 'basis_json', 'look_json')


def _next_record(conn, row: dict, new: dict, uid) -> tuple[str, dict | None]:
    """(the record once `uid` has changed what it should give to `new`, the confirmed state to put back when `new` is again what was last confirmed and an edit sent
    it back). Changing it adds its writer to who changed it since it was last confirmed; putting it back to what was last confirmed empties that."""
    kept = _kept(row) or {}
    confirmed, was = kept.get('confirmed'), kept.get('was')
    by = _changers(conn, row)
    if row['state'] == 'confirmed':   # this edit sends it back: keep what it was, to put back
        confirmed = _content(row)
        raw = dict(zip(('basis_json', 'look_json'), conn.execute('SELECT basis_json, look_json FROM needed_question WHERE id = ?', (row['id'],)).fetchone()))
        was = {k: raw[k] if k in raw else row[k] for k in _WAS}
    content = _content(new)
    if confirmed is not None and content == confirmed:
        by = set()
    elif uid is not None:
        by = by | {uid}
    record = {'by': sorted(by), 'of': fingerprint(content), **({'confirmed': confirmed} if confirmed is not None else {}), **({'was': was} if was else {})}
    return json.dumps(record, ensure_ascii=False, sort_keys=True), (was if was and content == confirmed else None)


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


def _reads(asks: list[dict]) -> dict | None:
    """What these asks read, at the versions they read it: the datasets and definitions their answers used, and the definitions a refusal named. None for none."""
    datasets, definitions = {}, {}
    for a in asks:
        datasets.update(a.get('datasets') or {})
        for d in [*(a.get('definitions') or []), *(b for b in a.get('blocking') or [] if b.get('id'))]:
            definitions[d['id']] = {'name': d['name'], 'version': d.get('version')}
    return {'datasets': datasets, 'definitions': definitions} if datasets or definitions else None


def _answered_basis(conn, row: dict) -> dict | None:
    """What the expected answer read, from the last run's asks of this question (worded as it is now) that gave what is expected."""
    found = conn.execute('SELECT question, result_json FROM needed_result WHERE question_id = ? ORDER BY run_id DESC LIMIT 1', (row['id'],)).fetchone()
    if found is None or found[0] != row['question']:
        return None
    expect = _expect_of(row)
    return _reads([a for a in json.loads(found[1]).get('asks') or [] if _class(expect, a) == 'right'])


def confirm(conn, user: dict | None, payload: dict) -> dict:
    """{id, version}: confirm what the question should give. While two-person confirmation is on, not by the person who wrote it. A person signed in to the page
    only (access.PERSON_ONLY_POSTS): "confirmed by" carries their name. What the expected answer read is recorded when the last run gave it; else the next
    passing run records it."""
    _reader(conn, user)
    _person(user)
    with transaction(conn):
        row = _found(conn, payload)
        if row['state'] == 'none':
            raise QaRefused(tr('先写它应该给出什么（一个数，或者必须拒答），再确认', 'First write what it should give (a number, or that it must be refused), then confirm it'))
        if row['state'] == 'confirmed':
            raise QaRefused(tr('这个期望已经确认了', 'This expectation is already confirmed'))
        own = user is not None and user['id'] in _barred(conn, row)   # wrote it, or changed it since it was last confirmed
        if own and two_person(conn)['active']:
            raise QaRefused(_held(conn, row) or tr('这一条是你自己提的，要另一位来确认', 'You put this forward yourself, so someone else must confirm it'), 403)
        basis = _answered_basis(conn, row)
        record = json.dumps({'by': [], 'of': fingerprint(_content(row)), 'confirmed': _content(row)}, ensure_ascii=False, sort_keys=True)
        conn.execute("UPDATE needed_question SET state = 'confirmed', version = version + 1, expect_version = expect_version + 1, confirmed_by = ?, confirmed_by_user_id = ?, confirmed_at = ?, self_confirmed = ?, "
                     'basis_json = ?, look_json = NULL, changed_json = ? WHERE id = ?', (_name(user), _uid(user), now_text(), int(own), json.dumps(basis, ensure_ascii=False) if basis else None, record, row['id']))
        _log(conn, user, row['id'], 'confirmed', before=_logged(row), after={**_logged({**row, 'state': 'confirmed'}), **({'self_confirmed': True} if own else {})})
    return _one(conn, user, row['id'])


# --- running ------------------------------------------------------------------------------------------------------------------------------------------------

class _RunGateway:
    """The service's model, for one run: each call is charged on the run's row as it goes out, and its line in the model call log is marked as this run's."""

    def __init__(self, gateway, conn, run_id: int):
        self._gateway, self._conn, self.run_id, self.calls, self.failure = gateway, conn, run_id, 0, None

    @property
    def model(self):
        return getattr(self._gateway, 'model', None)

    def complete_json(self, **request):
        self.calls += 1
        self._conn.execute('UPDATE needed_run SET calls = ? WHERE id = ?', (self.calls, self.run_id))
        try:
            return self._gateway.complete_json(**request)
        except Exception as exc:   # kept in its own words, for the line that says why the run stopped
            self.failure = str(exc)[:200]
            raise

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


def _start(conn, user: dict | None, repeats: int, count: int) -> tuple[int, str]:
    """(the run's id, its token): the row, written only when no other run is going and the runs' budget has room for every call this one may make."""
    planned = count * repeats
    with transaction(conn):
        _close_cut_off(conn)
        if _running_now(conn):
            raise QaRefused(_busy_text(), 409)
        used = _used(conn)
        if used + planned > SUITE_LIMIT:
            raise QaRefused(tr(f'运行的模型调用在任意 {SUITE_HOURS} 小时内最多 {SUITE_LIMIT} 次：已经用了 {used} 次，还剩 {max(0, SUITE_LIMIT - used)} 次，这次最多要 {planned} 次'
                               f'（{count} 个问题，每个问 {repeats} 次）。少问几次，或者晚些再跑。',
                               f'Runs may make {SUITE_LIMIT} model calls in any {SUITE_HOURS} hours. {used} are used, so {max(0, SUITE_LIMIT - used)} are left, and this run could make {planned} '
                               f'({count} questions, each asked {repeats} {"time" if repeats == 1 else "times"}). Ask fewer times, or run it later.'), 429)
        owner = uuid.uuid4().hex
        cursor = conn.execute("INSERT INTO needed_run(by_name, by_user_id, started_at, status, repeats, planned, calls, prompt_version, owner) VALUES (?, ?, ?, 'running', ?, ?, 0, ?, ?)",
                              (_name(user), _uid(user), now_text(), repeats, planned, QUESTION_PROMPT_VERSION, owner))
        with _LIVE_LOCK:
            _LIVE.add(owner)
        return cursor.lastrowid, owner


def _blocking(conn, result: dict) -> list[dict]:
    """What a refusal of the gate names: each definition not confirmed or waiting (with its version now and who can confirm it), or what the query left out."""
    if result['status'] == 'definition_unmet':
        return [{'kind': 'unmet', 'name': u.get('definition'), 'why': u.get('why')} for u in result.get('unmet') or [] if isinstance(u, dict)]
    refusal = result.get('refusal') or {}
    if result['status'] != 'refused' or refusal.get('kind') not in ('unsettled', 'unwalkable'):
        return []
    out = []
    for d in refusal.get('definitions', []):
        if isinstance(d, dict) and d.get('id'):
            row = element_row(conn, d['id'])
            out.append({**{k: d.get(k) for k in ('id', 'kind', 'name', 'state', 'who_can_confirm')}, 'version': row['version'] if row else None})
    return out


def _ask_said(conn, result: dict) -> dict:
    """What one ask came back as, kept with the run: the number, or the refusal with what blocks it; and what it read."""
    answered = result['status'] in ANSWERED
    return {'status': result['status'], 'number': _plain(answer_number(result)) if answered else None, 'reason': None if answered else result.get('reason'),
            'blocking': _blocking(conn, result) if result['status'] in GATE else [], 'query_text': result.get('query_text'), 'datasets': dict(result.get('datasets') or {}),
            'definitions': [{'id': d['id'], 'name': d['name'], 'version': d['version']} for d in result.get('definitions') or []], 'model': result.get('model')}


def _class(expect: dict | None, a: dict) -> str:
    """One ask against the expectation: 'right', 'wrong' (an answer that is not the expected one), 'gate' (a refusal of the gate that is not the expected one) or
    'none' (no answer and no refusal of the gate)."""
    gate, answered = a['status'] in GATE, a['status'] in ANSWERED
    if expect is None:
        return 'gate' if gate else 'none' if not answered else 'wrong'
    if expect['kind'] == 'number':
        return 'right' if answered and same_number(expect['value'], a['number']) else 'wrong' if answered else 'gate' if gate else 'none'
    named = expect.get('blocker') is None or any(expect['blocker'] in (b.get('id'), b.get('name')) for b in a['blocking'])
    return 'right' if gate and named else 'wrong' if answered else 'gate' if gate else 'none'


def _moved(conn, basis: dict | None) -> list[dict]:
    """What the expected answer read that has another version now (or is gone)."""
    if not basis:
        return []
    out = []
    for name, version in basis['datasets'].items():
        now = current_dataset(conn, name)
        if (now['version'] if now else None) != version:
            out.append({'kind': 'dataset', 'name': name, 'from': version, 'to': now['version'] if now else None})
    for element_id, d in basis['definitions'].items():
        now = element_row(conn, element_id)
        if (now['version'] if now else None) != d['version']:
            out.append({'kind': 'definition', 'name': d['name'], 'from': d['version'], 'to': now['version'] if now else None})
    return out


def _reads_otherwise(basis: dict | None, asks: list[dict]) -> dict | None:
    """{'now', 'not_now'}: the definitions the answers read now that the expected answer did not, and the other way round; None when they read the same."""
    answered = [a for a in asks if a['status'] in ANSWERED]
    if not basis or not answered:
        return None
    now = {d['id']: d['name'] for a in answered for d in a['definitions']}
    then = {k: d['name'] for k, d in basis['definitions'].items()}
    added, gone = [now[k] for k in now if k not in then], [then[k] for k in then if k not in now]
    return {'now': added, 'not_now': gone} if added or gone else None


def _distinct(asks: list[dict]) -> list[dict]:
    out = {}
    for a in asks:
        key = ('number', a['number']) if a['number'] is not None else ('status', a['status'])
        out.setdefault(key, {'number': a['number'], 'status': a['status'], 'times': 0})['times'] += 1
    return list(out.values())


def judge(conn, row: dict, asks: list[dict]) -> dict:
    """One question's outcome in a run, from its asks and its expectation as it stood when the run began."""
    expect = _expect_of(row) if row['state'] == 'confirmed' else None
    classes = [_class(expect, a) for a in asks]
    gate = next((a for a, c in zip(asks, classes) if c == 'gate'), None)
    none = next((a for a, c in zip(asks, classes) if c == 'none'), None)
    out = {'outcome': None, 'asked': len(asks), 'right': None, 'distinct': _distinct(asks), 'expected': expect, 'asks': asks, 'judged_against': _judged_against(row)}
    if expect is None:
        return {**out, 'outcome': 'no_expectation', 'answer': {k: asks[0][k] for k in ('status', 'number', 'reason', 'query_text')}, 'blocking': asks[0]['blocking']}
    out['right'] = classes.count('right')
    otherwise = _reads_otherwise(row['basis'], asks)
    if otherwise:
        out['reads_otherwise'] = otherwise
    if out['right'] == len(asks):
        return {**out, 'outcome': 'passes'}
    if 'wrong' in classes:
        moved = _moved(conn, row['basis'])
        return {**out, 'outcome': 'needs_look' if moved else 'differs', 'moved': moved}
    if gate is not None:   # refused by the gate, not the way expected: what blocks it; never "differs"
        return {**out, 'outcome': 'refused', 'reason': gate['reason'], 'blocking': gate['blocking']}
    return {**out, 'outcome': 'no_answer', 'reason': none['reason']}


def _prepare(conn, gateway, user: dict | None, payload: dict) -> tuple[list[dict], int]:
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
    return rows, repeats


def run(conn, gateway, user: dict | None, payload: dict) -> dict:
    """{repeats?}: ask every question on the list 1 to MAX_REPEATS times (default 1) as this person and store what each came back as, before returning the list
    as listing() reads it. Refused (403) to anyone but a builder or an admin whom nothing limits, to a token and to a demo guest; 400 for an empty list, 503
    without a model, 409 while another run goes, 429 when the runs' budget has no room for every call this one may make."""
    rows, repeats = _prepare(conn, gateway, user, payload)
    run_id, owner = _start(conn, user, repeats, len(rows))
    _execute(conn, gateway, user, run_id, owner, rows, repeats)
    return listing(conn, user, True)


def start(conn, gateway, user: dict | None, payload: dict, connect) -> dict:
    """The same as run(), refused the same way, but the asking goes on in the service after this returns (a run of many calls outlives a proxy's timeout); the
    list returned says it is running. `connect()` opens the workspace for the run."""
    rows, repeats = _prepare(conn, gateway, user, payload)
    run_id, owner = _start(conn, user, repeats, len(rows))
    context = contextvars.copy_context()   # the run says what it says in the language of the person who started it

    def go():
        own = connect()
        try:
            _execute(own, gateway, user, run_id, owner, rows, repeats)
        finally:
            own.close()
    try:
        threading.Thread(target=context.run, args=(go,), name=f'needed-run-{run_id}', daemon=True).start()
    except BaseException:
        with _LIVE_LOCK:
            _LIVE.discard(owner)
        raise
    return listing(conn, user, True)


def _execute(conn, gateway, user: dict | None, run_id: int, owner: str, rows: list[dict], repeats: int) -> None:
    """Ask each question, judge it and store the run once. A model that cannot be reached, or any error, stops it: the questions not asked come back as not run,
    and the run is closed as stopped with the calls it made."""
    counted = _RunGateway(gateway, conn, run_id)
    judged, stopped, model = {}, None, None
    try:
        for row in rows:
            asks = []
            for _ in range(repeats if stopped is None else 0):
                try:
                    said = _ask_said(conn, ask(conn, counted, user, row['question'], keep=False))
                except QaRefused as exc:
                    if exc.status in (502, 503):   # the model could not be reached: nothing more is asked
                        stopped = tr(f'模型连不上，运行停了（{counted.failure or exc}）', f'The model could not be reached, so the run stopped ({counted.failure or exc})')
                        break
                    said = {'status': 'not_asked', 'number': None, 'reason': str(exc), 'blocking': [], 'query_text': None, 'datasets': {}, 'definitions': [], 'model': None}
                model = model or said['model']
                asks.append(said)
            if stopped is not None:
                judged[row['id']] = (row, _not_run(row))
            else:
                judged[row['id']] = (row, judge(conn, row, asks))
    except Exception:   # whatever stopped it, the run is closed with what it asked, so the list is not left running
        traceback.print_exc()
        stopped = tr('这次运行出错停了，详情见服务日志', 'This run stopped on an error; see the service log')
        for row in rows:
            judged.setdefault(row['id'], (row, _not_run(row)))
    finally:
        try:
            _finish(conn, user, run_id, counted.calls, model, stopped, judged)
        finally:
            with _LIVE_LOCK:
                _LIVE.discard(owner)


def _not_run(row: dict) -> dict:
    return {'outcome': 'not_run', 'asked': 0, 'right': None, 'distinct': [], 'expected': _expect_of(row) if row['state'] == 'confirmed' else None, 'judged_against': _judged_against(row)}


def _finish(conn, user: dict | None, run_id: int, calls: int, model, stopped, judged: dict) -> None:
    """Store the run once: what each question came back as; a passing question's expectation now stands on what this run read; every expectation that needs another
    look goes back for a person (unless it was changed meanwhile)."""
    with transaction(conn):
        for qid, (row, result) in judged.items():
            kept = conn.execute('INSERT INTO needed_result(run_id, question_id, question, outcome, result_json) SELECT ?, ?, ?, ?, ? WHERE EXISTS (SELECT 1 FROM needed_question WHERE id = ?)',
                                (run_id, qid, row['question'], result['outcome'], json.dumps(result, ensure_ascii=False), qid)).rowcount
            if not kept:   # it went from the list while the run went
                continue
            if result['outcome'] == 'passes' and (basis := _reads(result['asks'])):
                conn.execute("UPDATE needed_question SET basis_json = ? WHERE id = ? AND version = ? AND state = 'confirmed'", (json.dumps(basis, ensure_ascii=False), qid, row['version']))
            if result['outcome'] == 'needs_look':
                changed = conn.execute("UPDATE needed_question SET state = 'needs_look', version = version + 1, look_json = ? WHERE id = ? AND version = ? AND state = 'confirmed'",
                                       (json.dumps(result['moved'], ensure_ascii=False), qid, row['version'])).rowcount
                if changed:
                    _log(conn, user, qid, 'needs_look', before=_logged(row), after={'state': 'needs_look', 'moved': result['moved'], 'run': run_id})
        conn.execute('UPDATE needed_run SET status = ?, finished_at = ?, calls = ?, model = ?, note = ? WHERE id = ?',
                     ('stopped' if stopped is not None else 'done', now_text(), calls, model, stopped, run_id))
        log_line(conn, _name(user), f'needed-run:{run_id}', 'run', after={'calls': calls, 'questions': len(judged), 'stopped': stopped is not None}, user_id=_uid(user))

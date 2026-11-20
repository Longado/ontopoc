"""Schedules: a source's tables pulled again, or a pipeline run again, on a clock (every hour, every day, every week, in a named time zone) or when its
input has a new version (pipelines only: a source has nothing upstream).

The clock is simple and has no state beyond one value: `last_slot`, the latest scheduled moment already acted on. Each minute `tick` asks, for every schedule,
"what is the latest slot at or before now?"; when that is newer than last_slot the schedule is due, last_slot moves to it first (so a run that fails does not come
back every minute), and the run starts. A service that was off for a day runs a daily schedule once on return, not once per missed day. A schedule made at 09:00
for "daily 08:00" first runs the next morning.

"upstream" is the same idea on versions: the schedule keeps the input versions it last acted on and is due when they differ.

Runs never overlap: a schedule whose target is still being pulled or run is logged as skipped. A scheduled run only runs a confirmed pipeline (a pipeline that
needs another look is skipped, and says so), and what it writes is checked like any new version: confirmed definitions that read a changed dataset go to
needs_look with the cause 数据变了 (recheck_after_write, the same path an upload takes).

Whose authority a schedule has. The person who made it: it keeps their account, and each run is made as that person, with what they may see and the role they have
now. A maker who has lost sight of the dataset or pipeline, was disabled, or is a viewer now, makes a run that is skipped and says why. Making one needs sight of
what it is for (what is kept from the person reads as what is not there); changing, switching off or deleting one is the maker's or an admin's. A pipeline's run goes the
way a manual run goes: the model is asked first without the lock (fill_answers, with its cap), then the run is written under it.
"""
from __future__ import annotations

import json
import re
import sys
import threading
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ontology_poc_generator.lang import tr
from ontology_poc_generator.accounts import get_user, user_count
from ontology_poc_generator.object_types import PIPELINE_PREFIX, element_row, one_telling
from ontology_poc_generator.type_access import dataset_hidden
from ontology_poc_generator.workspace_sources import (
    internal_error, NAME_LIMIT, NotFound, _binding, _row as _source_row, claimed, finish_run, is_admin, log_write, now_text, refresh_runs, refresh_table, start_run)

CADENCES = ('hourly', 'daily', 'weekly', 'upstream')
WEEKDAYS = ('周一', '周二', '周三', '周四', '周五', '周六', '周日')
WEEKDAYS_EN = ('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')
_TIME = re.compile(r'([01]\d|2[0-3]):([0-5]\d)', re.ASCII)


class Forbidden(ValueError):
    """The schedule is there for this person to see but is another person's to change."""


def who_of(schedule: dict) -> str:
    """How a run of a schedule signs: the schedule and the person it runs as."""
    return f'定时：{schedule["name"]}（{schedule["created_by"]}）' if schedule['created_by'] else f'定时：{schedule["name"]}'


def maker_of(conn, s: dict) -> tuple[dict | None, str | None]:
    """(the account a schedule runs as, None) or (None, why it may not run). The workspace without accounts runs as the local admin; a schedule made before makers
    were kept, in a workspace that has accounts, runs as nobody until someone makes it again."""
    maker_id = s['created_by_user_id']
    if maker_id is None:
        if user_count(conn):
            return None, tr('这个调度没有记下是谁建的，不能再自动跑；请让它的主人重建', 'This schedule has no recorded maker, so it can no longer run on its own. Ask its owner to recreate it')
        from ontology_poc_generator.auth_http import LOCAL_USER   # no accounts to look up: the one local person
        return LOCAL_USER, None
    user = get_user(conn, maker_id)
    if user is None:
        return None, tr('建这个调度的账号已经不在了，不能再自动跑', 'The account that made this schedule no longer exists, so it can no longer run on its own')
    if user['disabled']:
        return None, tr('建这个调度的人的账号已停用，不再自动跑；换人重建，或让管理员接手', 'The account that made this schedule is disabled, so it no longer runs on its own. Recreate it under another account, or ask an admin to take it over')
    if user['role'] == 'viewer':
        return None, tr('建这个调度的人现在只有查看权限，不再自动跑', 'The person who made this schedule can now only view, so it no longer runs on its own')
    return user, None


def cadence_text(s: dict) -> str:
    if s['cadence'] == 'upstream':
        return tr('上游更新时', 'When upstream updates')
    if s['cadence'] == 'hourly':
        when = tr(f'每小时的第 {s["minute"]} 分', f'At minute {s["minute"]} of every hour')
    else:
        clock = f'{s["hour"]:02d}:{s["minute"]:02d}'
        when = tr(f'每天 {clock}', f'Every day at {clock}') if s['cadence'] == 'daily' else tr(f'每{WEEKDAYS[s["weekday"]]} {clock}', f'Every {WEEKDAYS_EN[s["weekday"]]} at {clock}')
    return tr(f'{when}（{s["tz"]}）', f'{when} ({s["tz"]})')


# --- the clock -------------------------------------------------------------------------------------------------------------------------------------

def slot_at_or_before(s: dict, now: datetime) -> datetime | None:
    """The latest scheduled moment (UTC) not after `now`; None for a schedule that is not on a clock."""
    if s['cadence'] == 'upstream':
        return None
    local = now.astimezone(ZoneInfo(s['tz']))
    if s['cadence'] == 'hourly':
        slot = local.replace(minute=s['minute'], second=0, microsecond=0)
        back = timedelta(hours=1)
    elif s['cadence'] == 'daily':
        slot = local.replace(hour=s['hour'], minute=s['minute'], second=0, microsecond=0)
        back = timedelta(days=1)
    else:
        slot = (local - timedelta(days=(local.weekday() - s['weekday']) % 7)).replace(hour=s['hour'], minute=s['minute'], second=0, microsecond=0)
        back = timedelta(days=7)
    as_utc = lambda moment: moment.astimezone(timezone.utc)   # compared as instants: a wall-clock time that a daylight-saving change skips or repeats still orders correctly
    return as_utc(slot) if as_utc(slot) <= now else as_utc(slot - back)


def next_slot(s: dict, now: datetime) -> datetime | None:
    """The first scheduled moment after `now`."""
    last = slot_at_or_before(s, now)
    if last is None:
        return None
    local = last.astimezone(ZoneInfo(s['tz']))
    step = {'hourly': timedelta(hours=1), 'daily': timedelta(days=1), 'weekly': timedelta(days=7)}[s['cadence']]
    following = (local + step).astimezone(timezone.utc)
    return following if following > now else (local + 2 * step).astimezone(timezone.utc)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def runnable(row: dict) -> bool:
    """Whether a pipeline may be run by a schedule: its definition has been confirmed by someone. A pipeline whose confirmation went stale because the data it reads
    moved (cause 数据变了, on itself) still is: that move is what the run is for, and a schedule that waited for a person to confirm after every new version could
    never follow its upstream. One whose logic was changed since, or that was never confirmed, is not."""
    return row['state'] == 'confirmed' or (row['state'] == 'needs_look' and row['cause'] == 'data' and row['via'] == 'self')


# --- reading and setting up ------------------------------------------------------------------------------------------------------------------------

def _rows(conn, where: str = '', args: tuple = ()) -> list[dict]:
    cursor = conn.execute(f'SELECT * FROM schedule {where} ORDER BY name', args)
    columns = [c[0] for c in cursor.description]
    return [dict(zip(columns, r)) for r in cursor.fetchall()]


def _targets(conn, s: dict) -> list[str]:
    """The datasets this schedule writes: the tables of a source it reads (its scope, or every table read as a dataset), or a pipeline's outputs."""
    if s['kind'] == 'source':
        try:
            source = _source_row(conn, s['target'])
        except KeyError:
            return []
        scope = json.loads(s['scope_json']) if s['scope_json'] else None
        found = [b for t in (scope if scope is not None else [r[0] for r in conn.execute('SELECT table_name FROM source_table WHERE source_id = ? ORDER BY table_name', (source['id'],))])
                 if (b := _binding(conn, source['id'], t))]
        return [b['dataset'] for b in found]
    row = element_row(conn, f'{PIPELINE_PREFIX}{s["target"]}')
    return [st['name'] for st in json.loads(row['content_json'])['spec']['steps'] if st['type'] == 'output'] if row else []


def _mine(s: dict, user: dict | None) -> bool:
    return s['created_by_user_id'] == (user['id'] if user else None)


def _shown(conn, s: dict, user: dict | None) -> bool:
    """Whether this person is told the schedule exists: a pipeline they may see, or a source's schedule that writes at least one dataset they may see (or none yet)."""
    if is_admin(user):
        return True
    if s['kind'] == 'pipeline':
        from ontology_poc_generator.workspace_pipelines import pipeline_visible   # workspace_pipelines reads datasets, not schedules
        row = element_row(conn, f'{PIPELINE_PREFIX}{s["target"]}')
        return row is not None and pipeline_visible(conn, row, user)
    targets = _targets(conn, s)
    return not targets or any(not dataset_hidden(conn, d, user) for d in targets)


def schedule_view(conn, s: dict, user: dict | None = None, now: datetime | None = None) -> dict:
    """A schedule as its page reads it by this person: what it does and when, the latest run, the last run that changed data and who made it, the datasets it writes
    that they may see, its scope, whether it is theirs (`mine`) and whether they may change it (`can_change`: the maker or an admin)."""
    now = now or datetime.now(timezone.utc)
    runs = refresh_runs(conn, schedule_id=s['id'], limit=200, user=user)
    changed = next((r for r in runs if r['changed']), None)
    upcoming = next_slot(s, now) if s['enabled'] else None
    return {'id': s['id'], 'name': s['name'], 'kind': s['kind'], 'target': s['target'], 'scope': json.loads(s['scope_json']) if s['scope_json'] else None,
            'cadence': s['cadence'], 'minute': s['minute'], 'hour': s['hour'], 'weekday': s['weekday'], 'tz': s['tz'], 'when': cadence_text(s), 'enabled': bool(s['enabled']),
            'next_at': upcoming.isoformat(timespec='seconds') if upcoming else None, 'targets': [d for d in _targets(conn, s) if not dataset_hidden(conn, d, user)],
            'created_by': s['created_by'], 'created_at': s['created_at'], 'mine': _mine(s, user), 'can_change': _mine(s, user) or is_admin(user),
            'latest_run': runs[0] if runs else None, 'last_change': {'at': changed['finished_at'], 'by': changed['who'], 'dataset': changed['dataset'], 'version': changed['version']} if changed else None}


def list_schedules(conn, user: dict | None = None, now: datetime | None = None) -> list[dict]:
    return [schedule_view(conn, s, user, now) for s in _rows(conn) if _shown(conn, s, user)]


def schedule_runs(conn, schedule_id: int, user: dict | None = None) -> list[dict]:
    """The runs one schedule logged, as this person may read them; a schedule they are not told exists is not there."""
    found = _rows(conn, 'WHERE id = ?', (schedule_id,))
    if not found or not (_mine(found[0], user) or _shown(conn, found[0], user)):
        raise KeyError(schedule_id)
    return refresh_runs(conn, schedule_id=schedule_id, user=user)


def _fields(conn, payload: dict, user: dict | None) -> dict:
    name = str(payload.get('name') or '').strip()
    if not name or len(name) > NAME_LIMIT:
        raise ValueError(tr(f'调度的名字要写 1 到 {NAME_LIMIT} 个字', f'A schedule name must be 1 to {NAME_LIMIT} characters'))
    kind, target, cadence = payload.get('kind'), str(payload.get('target') or ''), payload.get('cadence')
    if kind not in ('source', 'pipeline'):
        raise ValueError(tr('调度的对象只能是数据源或管道', 'A schedule can only target a source or a pipeline'))
    if cadence not in CADENCES:
        raise ValueError(tr('触发方式只有每小时、每天、每周、上游更新时', 'The trigger is hourly, daily, weekly or when upstream updates'))
    if cadence == 'upstream' and kind != 'pipeline':
        raise ValueError(tr('“上游更新时”只能用在管道上：数据源的上游是外面的数据库，我们看不到它什么时候变', '“When upstream updates” only works on a pipeline: a source reads from an outside database, and we cannot see when it changes'))
    scope = payload.get('scope')
    if kind == 'source':
        try:
            source = _source_row(conn, target)
        except KeyError:
            raise ValueError(tr('没有这个数据源', 'No such source')) from None
        if scope is not None:
            if not (isinstance(scope, list) and scope and all(isinstance(t, str) for t in scope)):
                raise ValueError(tr('范围要写成表名的列表；不写就是这个数据源里读成数据集的全部表', 'The scope must be a list of table names. Leave it out to use every table of this source that is read as a dataset'))
            usable = [(b := _binding(conn, source['id'], t)) is not None and not dataset_hidden(conn, b['dataset'], user) for t in scope]
            if not all(usable):   # a table that is not there, one not read as a dataset yet and one read as a dataset kept from this person: one answer, no table named
                raise ValueError(tr('范围里有的表还没有读成数据集，或者读成了你看不到的数据集，不能定时刷新。先读一次', 'Some tables in the scope are not read as datasets yet, or are read as datasets you cannot see, so they cannot be refreshed on a schedule. Read them once first'))
    else:
        scope = None
        from ontology_poc_generator.workspace_pipelines import pipeline_visible   # workspace_pipelines reads datasets, not schedules
        row = element_row(conn, f'{PIPELINE_PREFIX}{target}')
        if row is None or not pipeline_visible(conn, row, user):
            raise NotFound(tr('没有这条管道', 'No such pipeline'))
        if not runnable(row):
            raise ValueError(tr(f'管道“{target}”现在是“{row["state"]}”，只有已确认的管道才能定时跑：它的结果会没人看着就写进数据集', f'Pipeline “{target}” is now “{row["state"]}”. Only a confirmed pipeline can run on a schedule, because its results are written to datasets with nobody watching'))
    tz = str(payload.get('tz') or '')
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise ValueError(tr('时区要写成 Asia/Shanghai、Asia/Taipei、UTC 这样的名字', 'The time zone must be a name like Asia/Shanghai, Asia/Taipei or UTC')) from None
    minute = hour = weekday = None
    if cadence == 'hourly':
        minute = payload.get('minute', 0)
        if isinstance(minute, bool) or not isinstance(minute, int) or not 0 <= minute <= 59:
            raise ValueError(tr('每小时的第几分要写成 0 到 59', 'The minute of the hour must be 0 to 59'))
    elif cadence in ('daily', 'weekly'):
        found = _TIME.fullmatch(str(payload.get('time') or ''))
        if not found:
            raise ValueError(tr('时间要写成 08:30 这样', 'The time must look like 08:30'))
        hour, minute = int(found.group(1)), int(found.group(2))
        if cadence == 'weekly':
            weekday = payload.get('weekday')
            if isinstance(weekday, bool) or not isinstance(weekday, int) or not 0 <= weekday <= 6:
                raise ValueError(tr('星期要写成 0（周一）到 6（周日）', 'The weekday must be 0 (Monday) to 6 (Sunday)'))
    return {'name': name, 'kind': kind, 'target': target, 'scope_json': json.dumps(scope, ensure_ascii=False) if scope is not None else None,
            'cadence': cadence, 'minute': minute, 'hour': hour, 'weekday': weekday, 'tz': tz}


def _inputs_of(conn, s: dict) -> dict | None:
    if s['kind'] != 'pipeline' or s['cadence'] != 'upstream':
        return None
    from ontology_poc_generator.workspace_pipelines import _inputs_now   # workspace_pipelines reads datasets, not schedules
    row = element_row(conn, f'{PIPELINE_PREFIX}{s["target"]}')
    return _inputs_now(conn, json.loads(row['content_json'])) if row else None


def create_schedule(conn, payload: dict, who: str | None, user: dict | None = None, now: datetime | None = None) -> dict:
    """{name, kind (source|pipeline), target, cadence (hourly|daily|weekly|upstream), minute | time + weekday, tz, scope?}. It starts counting now: the first run is
    the next slot (or, for "upstream", the next new input version). It is this person's, and runs as them."""
    fields = _fields(conn, payload, user)
    if conn.execute('SELECT 1 FROM schedule WHERE name = ?', (fields['name'],)).fetchone():
        raise ValueError(tr(f'已经有叫“{fields["name"]}”的调度', f'A schedule named “{fields["name"]}” already exists'))
    now = now or datetime.now(timezone.utc)
    signer, stamp = str(who or '').strip() or '未署名', now_text()
    draft = {**fields, 'id': None, 'enabled': 1}
    slot = slot_at_or_before(draft, now)
    seen = _inputs_of(conn, draft)
    created = conn.execute('INSERT INTO schedule(name, kind, target, scope_json, cadence, minute, hour, weekday, tz, enabled, last_slot, upstream_seen_json, created_by, created_by_user_id, '
                           'created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)',
                           (*(fields[k] for k in ('name', 'kind', 'target', 'scope_json', 'cadence', 'minute', 'hour', 'weekday', 'tz')), slot.isoformat() if slot else None,
                            json.dumps(seen) if seen is not None else None, signer, user['id'] if user else None, stamp, stamp)).lastrowid
    log_write(conn, signer, f'schedule:{fields["name"]}', 'created', {'kind': fields['kind'], 'target': fields['target'], 'cadence': fields['cadence']})
    return schedule_view(conn, next(s for s in _rows(conn, 'WHERE id = ?', (created,))), user, now)


def _owned(conn, payload: dict, user: dict | None) -> dict:
    """The schedule the request means, when this person may change it: the maker or an admin. KeyError when there is no such schedule or it is not one they are told
    about (the same for both); Forbidden when they may see it but it is another's."""
    found = _rows(conn, 'WHERE id = ?', (payload.get('id'),))
    if not found:
        raise KeyError(payload.get('id'))
    s = found[0]
    if _mine(s, user) or is_admin(user):
        return s
    if not _shown(conn, s, user):
        raise KeyError(payload.get('id'))
    raise Forbidden(tr('这个调度是别人建的：只有建它的人或管理员能改、停用或删除它', 'This schedule was made by someone else. Only its maker or an admin can change, disable or delete it'))


def update_schedule(conn, payload: dict, who: str | None, user: dict | None = None, now: datetime | None = None) -> dict:
    """{id, enabled} switches a schedule on or off; with the other fields (as in create_schedule) it changes what it does and counts from now. The maker's or an admin's."""
    old, now, signer = _owned(conn, payload, user), now or datetime.now(timezone.utc), str(who or '').strip() or '未署名'
    if set(payload) <= {'id', 'enabled', 'who'}:
        if not isinstance(payload.get('enabled'), bool):
            raise ValueError(tr('enabled 要写成 true 或 false', 'enabled must be true or false'))
        conn.execute('UPDATE schedule SET enabled = ?, updated_at = ? WHERE id = ?', (int(payload['enabled']), now_text(), old['id']))
        log_write(conn, signer, f'schedule:{old["name"]}', 'enabled' if payload['enabled'] else 'disabled')
        return schedule_view(conn, _rows(conn, 'WHERE id = ?', (old['id'],))[0], user, now)
    fields = _fields(conn, {**{k: old[k] for k in ('name', 'kind', 'target', 'tz', 'cadence', 'minute')}, 'scope': json.loads(old['scope_json']) if old['scope_json'] else None,
                            'time': f'{old["hour"]:02d}:{old["minute"]:02d}' if old['hour'] is not None else None, 'weekday': old['weekday'], **payload}, user)
    if fields['name'] != old['name'] and conn.execute('SELECT 1 FROM schedule WHERE name = ?', (fields['name'],)).fetchone():
        raise ValueError(tr(f'已经有叫“{fields["name"]}”的调度', f'A schedule named “{fields["name"]}” already exists'))
    slot = slot_at_or_before({**fields, 'id': old['id']}, now)
    seen = _inputs_of(conn, fields)
    conn.execute('UPDATE schedule SET name = ?, kind = ?, target = ?, scope_json = ?, cadence = ?, minute = ?, hour = ?, weekday = ?, tz = ?, last_slot = ?, upstream_seen_json = ?, updated_at = ? WHERE id = ?',
                 (*(fields[k] for k in ('name', 'kind', 'target', 'scope_json', 'cadence', 'minute', 'hour', 'weekday', 'tz')), slot.isoformat() if slot else None,
                  json.dumps(seen) if seen is not None else None, now_text(), old['id']))
    log_write(conn, signer, f'schedule:{fields["name"]}', 'updated', {'cadence': fields['cadence'], 'target': fields['target']})
    return schedule_view(conn, _rows(conn, 'WHERE id = ?', (old['id'],))[0], user, now)


def delete_schedule(conn, payload: dict, who: str | None, user: dict | None = None) -> dict:
    """The maker's or an admin's. Its runs stay in the log."""
    found = _owned(conn, payload, user)
    conn.execute('DELETE FROM schedule WHERE id = ?', (found['id'],))
    log_write(conn, str(who or '').strip() or '未署名', f'schedule:{found["name"]}', 'deleted')
    return {'name': found['name']}


# --- running ---------------------------------------------------------------------------------------------------------------------------------------

def _skip(conn, s: dict, reason: str, why: str, item: str = '') -> dict:
    return finish_run(conn, start_run(conn, s['kind'], s['target'], item, reason, who_of(s), s['id']), 'skipped', error=why)


def _run_source(conn, s: dict, reason: str, lock, user: dict) -> list[dict]:
    try:
        source = _source_row(conn, s['target'])
    except KeyError:
        return [_skip(conn, s, reason, tr('这个数据源已经不在了', 'This source no longer exists'))]
    scope = json.loads(s['scope_json']) if s['scope_json'] else [r[0] for r in conn.execute('SELECT table_name FROM source_table WHERE source_id = ? ORDER BY table_name', (source['id'],))]
    if not scope:
        return [_skip(conn, s, reason, tr('这个数据源里还没有读成数据集的表', 'This source has no tables read as datasets yet'))]
    out = []
    for table in scope:
        bound = _binding(conn, source['id'], table)
        if bound is None:
            out.append(_skip(conn, s, reason, tr(f'“{table}”已经不是数据集了（数据集被删了）', f'“{table}” is no longer a dataset (the dataset was deleted)'), table))
        elif dataset_hidden(conn, bound['dataset'], user):
            out.append(_skip(conn, s, reason, tr(f'建这个调度的人现在看不到“{table}”读成的数据集，没有刷新', f'The person who made this schedule can no longer see the dataset “{table}” is read as, so it was not refreshed'), table))
        else:
            out.append(refresh_table(conn, source, table, bound['dataset'], bound['mode'], bound['key_columns'], who_of(s), reason, lock, schedule_id=s['id'], user=user))
    return out


def _run_pipeline(conn, s: dict, reason: str, lock, engine, llm, user: dict) -> list[dict]:
    from ontology_poc_generator.workspace_pipelines import fill_answers, pipeline_visible, run_now   # workspace_pipelines reads datasets, not schedules
    row = element_row(conn, f'{PIPELINE_PREFIX}{s["target"]}')
    if row is None:
        return [_skip(conn, s, reason, tr('这条管道已经不在了', 'This pipeline no longer exists'))]
    if not pipeline_visible(conn, row, user):
        return [_skip(conn, s, reason, tr('建这个调度的人现在看不到这条管道，没有运行', 'The person who made this schedule can no longer see this pipeline, so it did not run'))]
    if not runnable(row):
        return [_skip(conn, s, reason, tr(f'管道现在是“{row["state"]}”，它的定义没有人确认过（或确认之后又改了），定时不跑它；确认后下一次再跑', f'The pipeline is now “{row["state"]}”: nobody has confirmed its definition (or it changed after it was confirmed), so the schedule does not run it. Confirm it and the next slot will run'))]
    with claimed(('pipeline', s['target'], '')) as got:
        if not got:
            return [_skip(conn, s, reason, tr('上一次运行还没结束，这次跳过', 'The last run has not finished, so this one is skipped'))]
        run_id = start_run(conn, 'pipeline', s['target'], '', reason, who_of(s), s['id'])
        try:
            request = {'id': s['target']}
            filled = fill_answers(conn, engine, request, user, llm)   # the model is asked first, without the lock (and at most the cap): the way a manual run goes
            with lock:   # the lock an upload takes; the run writes from the answers now kept
                done = run_now(conn, engine, request, who_of(s), user, llm, filled)
        except ValueError as exc:   # a refusal in words: the cap, a step that cannot run, a pipeline that changed since
            return [finish_run(conn, run_id, 'failed', error=str(exc))]
        except BaseException:
            finish_run(conn, run_id, 'failed', error=internal_error())
            raise
        written = done.get('outputs') or []
        return [finish_run(conn, run_id, 'success' if done['status'] == 'success' else 'failed', rows=sum(w['rows'] for w in written) if written else None,
                           dataset='、'.join(w['dataset'] for w in written) or None, version=written[0]['version'] if len(written) == 1 else None,
                           changed=any(w['created_version'] for w in written) if done['status'] == 'success' else None, error=done.get('error'),
                           detail={'pipeline_run': done['id'], 'outputs': written})]


def run_schedule(conn, s: dict, reason: str, lock, engine=None, llm=None) -> list[dict]:
    """Run what a schedule is for, now, as the person who made it, and return the runs it logged (one per table for a source, one for a pipeline). A maker who may
    not (disabled, a viewer now, gone) makes one run, skipped, that says why."""
    user, why = maker_of(conn, s)
    if user is None:
        return [_skip(conn, s, reason, why)]
    with one_telling(conn):   # every table a source schedule refreshes: one notice per person for the whole run
        return _run_source(conn, s, reason, lock, user) if s['kind'] == 'source' else _run_pipeline(conn, s, reason, lock, engine, llm, user)


def due(conn, s: dict, now: datetime) -> str | None:
    """'schedule' when the clock has passed a slot the schedule has not acted on, 'upstream' when an input has a new version; else None. Moves the schedule's
    memory (last_slot, the input versions) to what it is about to act on, so the same moment is never acted on twice."""
    if not s['enabled']:
        return None
    if s['cadence'] == 'upstream':
        now_inputs = _inputs_of(conn, s)
        if now_inputs is None or now_inputs == (json.loads(s['upstream_seen_json']) if s['upstream_seen_json'] else None):
            return None
        conn.execute('UPDATE schedule SET upstream_seen_json = ? WHERE id = ?', (json.dumps(now_inputs), s['id']))
        return 'upstream'
    slot = slot_at_or_before(s, now)
    if s['last_slot'] and slot <= _utc(s['last_slot']):
        return None
    conn.execute('UPDATE schedule SET last_slot = ? WHERE id = ?', (slot.isoformat(), s['id']))
    return 'schedule'


def tick(conn, lock, engine_factory=None, llm=None, now: datetime | None = None) -> list[dict]:
    """Once a minute: run every schedule that is due. Sources first, then pipelines, so a pipeline that runs "when its upstream updates" sees the pull that just
    happened in the same pass. Returns the runs logged. A failure of one schedule is in its own run and does not stop the others."""
    now = now or datetime.now(timezone.utc)
    runs = []
    for s in sorted(_rows(conn), key=lambda r: (r['kind'] != 'source', r['name'])):
        engine = None
        try:
            reason = due(conn, s, now)   # inside the try: a schedule whose time zone cannot be read is this schedule's trouble and not the others'
            if reason is None:
                continue
            engine = engine_factory() if (engine_factory and s['kind'] == 'pipeline') else None
            runs += run_schedule(conn, s, reason, lock, engine, llm)
        except Exception as exc:   # the run is logged as failed where it started; the next schedule still gets its turn, and the error is not lost
            print(f'schedule “{s["name"]}” stopped with {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)
        finally:
            if engine is not None:
                engine.close()
    return runs


def schedule_loop(run_due, stop: threading.Event) -> None:
    """Wake at the top of every minute and run what is due, until `stop` is set. An error in one pass is printed and the next minute tries again."""
    while not stop.wait(60 - time.time() % 60):
        try:
            run_due()
        except Exception as exc:
            print(f'schedule pass failed with {type(exc).__name__}: {exc}', file=sys.stderr, flush=True)

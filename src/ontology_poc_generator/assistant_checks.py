"""What the assistant's cards list as key assumptions and as the self-check, worked out by code from what a draft or a suggestion already contains.
No model is asked and no prompt changes: an assumption is a fact the result stands on (confirmed, with a link to the definition that confirms it) or a question nobody
has answered (open); the self-check names what ran and what did not. An open assumption blocks Apply, and only Apply, until it is answered."""
from __future__ import annotations

from datetime import datetime, timezone

from ontology_poc_generator.draft_receipts import peek, pipeline_fingerprint, type_fingerprint
from ontology_poc_generator.lang import tr

CONFIRMED, OPEN = 'confirmed', 'open'


def blocks_apply(assumptions: list[dict]) -> bool:
    return any(a['status'] == OPEN for a in assumptions)


def plan_assumptions(out: dict, answers: dict | None = None) -> list[dict]:
    """The pipeline draft's assumptions: each confirmed meaning it used (linked to its definition), each question the person answered (theirs), then the open questions."""
    found = [{'id': f'meaning:{c["column"]}|{c["meaning"]}', 'text': c['text'], 'status': CONFIRMED, 'definition': c.get('definition'), 'by': None} for c in out.get('cites') or []]
    open_ids = {q['id'] for q in out.get('questions') or []}
    for qid, values in (answers or {}).items():
        if qid in open_ids or not values:
            continue
        column, _, concept = qid.partition('|')
        chosen = ', '.join(f'"{v}"' for v in values)
        found.append({'id': f'answer:{qid}', 'text': tr(f'你选定：「{column}」里“{concept}”是 {"、".join(map(str, values))}', f'You chose {chosen} for "{concept}" in "{column}"') if concept
                      else tr(f'你选定：「{column}」是 {"、".join(map(str, values))}', f'You chose {chosen} for "{column}"'), 'status': CONFIRMED, 'definition': None, 'by': 'you'})
    found.extend({'id': f'question:{q["id"]}', 'question': q['id'], 'text': q['ask'], 'status': OPEN, 'evidence': q.get('evidence', '')} for q in out.get('questions') or [])
    return found


def plan_self_check(out: dict) -> dict:
    """{'done': [{key, text}], 'not_done': [{key, text}]} from what the draft carries: the check, the dry run, the row counts, the questions. It never says "verified"."""
    steps, check = out.get('steps') or [], out.get('check') or {}
    ok = bool(check.get('ok'))
    counted = bool(steps) and all(s.get('rows_out') is not None and s.get('rows_in') for s in steps)
    open_count = len(out.get('questions') or [])
    failing = sum(1 for s in steps if s.get('failures'))
    done, not_done = [], []
    if ok:
        done.append({'key': 'columns', 'text': tr('列、操作和函数都存在', 'Columns, operators and functions exist')})
    if ok and check.get('dry_run'):
        done.append({'key': 'dry', 'text': check['dry_run']})
    if counted:
        done.append({'key': 'counts', 'text': tr(f'{len(steps)} 步的行数都已算出', f'Row counts for each of the {len(steps)} steps')})
    if out.get('cites'):
        done.append({'key': 'cites', 'text': tr(f'用了 {len(out["cites"])} 条已确认的含义', f'Used {len(out["cites"])} confirmed meaning(s)')})
    if not ok:
        not_done.append({'key': 'failed', 'text': tr(f'核对没通过：{check.get("error", "")}', f'Check failed: {check.get("error", "")}')})
    if open_count:
        not_done.append({'key': 'open', 'text': tr(f'{open_count} 个待答的问题还没回答', f'{open_count} open question(s) not answered')})
    if failing:
        not_done.append({'key': 'stepFailures', 'text': tr(f'{failing} 步在现在的数据上有问题', f'{failing} step(s) have problems on the current data')})
    not_done.append({'key': 'fullRun', 'text': tr('在全部数据上运行', 'Run on all the data')})
    not_done.append({'key': 'saved', 'text': tr('还没有保存：管道里什么也没有', 'Saved: nothing is in a pipeline yet')})
    return {'done': done, 'not_done': not_done}


def type_assumptions(english_name: str, key: list[str], rows: int, code_columns: list[str]) -> list[dict]:
    """A suggested type's assumptions: its key, which the code checked on every row (confirmed), and each code column whose meanings nobody has confirmed (open)."""
    cols = ', '.join(key)
    found = [{'id': f'key:{english_name}', 'text': tr(f'主键（{cols}）在 {rows} 行里都不重复、也没有空值', f'The key ({cols}) is unique and filled on all {rows} rows'),
              'status': CONFIRMED, 'definition': f'objtype:{english_name}', 'by': None}]
    found.extend({'id': f'meanings:{english_name}:{c}', 'text': tr(f'还没有人确认“{c}”里各代码的含义', f'Nobody has confirmed what the codes in "{c}" mean'),
                  'status': OPEN, 'definition': f'enum:{english_name}:{c}'} for c in code_columns)
    return found


def type_self_check(kept: int, dropped: int) -> dict:
    done, not_done = [], []
    if kept:
        done.append({'key': 'checked', 'text': tr(f'数据集和列都存在，{kept} 个主键在全部行上都不重复、没有空值', 'Datasets and columns exist, and the key is unique and filled on all rows' if kept == 1 else f'Datasets and columns exist, and each of the {kept} keys is unique and filled on all rows')})
        done.append({'key': 'kept', 'text': tr(f'已存为 {kept} 份模型草稿（还没有提议人）', f'Kept {kept} as model drafts (no proposer yet)')})
        not_done.append({'key': 'confirmed', 'text': tr('还没有人确认：没有一个类型被确认', 'Confirmed: nobody has confirmed any type')})
    if dropped:
        not_done.append({'key': 'dropped', 'text': tr(f'{dropped} 条建议没通过核对，已剔除', f'{dropped} suggestion(s) failed the checks and were left out')})
    return {'done': done, 'not_done': not_done}


def drafted_mark(conn, payload: dict, who: str | None, user: dict | None, kind: str, saved, old: dict | None = None, target: str | None = None) -> dict | None:
    """The marker an object carries when it was applied from the assistant's draft: who applied it, when, and how. It is stored in the definition like its other metadata.

    The server decides, not the page: `assistant: true` marks nothing. The save must carry `draft_receipt`, the id the server issued with the draft (draft_receipts):
    live (24 hours), issued to this person, for this kind ('pipeline' or 'type'), for this target when it was issued for one, and not used before. A receipt is used up
    by the first save that carries it once that save is written (draft_receipts.spend at the call site); a save that fails leaves it for the retry. An invalid receipt is ignored silently: the save goes ahead without a marker, and keeps `old` (the marker the
    object already has). The saved content is compared with the fingerprint of what was drafted:
      pipeline (`saved` = the saved steps): every drafted step is there exactly as drafted -> how 'assistant'; some drafted step is there but any is changed or missing -> 'assistant-edited';
        none of the drafted steps is there -> no marker.
      type (`saved` = the saved definition): same dataset, key and set of columns as drafted -> 'assistant'; otherwise -> 'assistant-edited'."""
    receipt = payload.get('draft_receipt')
    got = peek(conn, receipt, user, kind)
    if got is None:
        return old
    drafted_target, fingerprint = got
    if drafted_target is not None and drafted_target != target:
        return old
    if kind == 'pipeline':
        now = pipeline_fingerprint([s for s in saved if isinstance(s, dict)])
        present = [i for i in fingerprint if i in now]
        if not present:
            return old
        how = 'assistant' if len(present) == len(fingerprint) and all(now[i] == fingerprint[i] for i in present) else 'assistant-edited'
    else:
        how = 'assistant' if type_fingerprint(saved) == fingerprint else 'assistant-edited'
    return {'by': who, 'at': datetime.now(timezone.utc).isoformat(timespec='seconds'), 'how': how}


def meanings_assumptions(english_name: str, columns: list[dict]) -> list[dict]:
    """The Meanings card's assumptions: a column whose meanings were confirmed stays as it is (confirmed, linked to them); each column with drafted meanings stands on a guess
    nobody has confirmed yet (open). The open ones do not stop Apply: Apply only puts the meanings forward, and a second builder confirms them."""
    found = []
    for c in columns:
        column = c['column']
        if c['confirmed']:
            found.append({'id': f'meanings:{english_name}:{column}', 'text': tr(f'“{column}”的含义已经确认，这次不改', f'The meanings of "{column}" are confirmed and are left as they are'),
                          'status': CONFIRMED, 'definition': f'enum:{english_name}:{column}', 'by': None})
        elif any(v['draft'] for v in c['values']):
            found.append({'id': f'meanings:{english_name}:{column}', 'text': tr(f'“{column}”里各代码的含义是模型的猜测，要另一位建设者确认', f'The meanings of the codes in "{column}" are the model\'s guess and need another builder to confirm'),
                          'status': OPEN, 'definition': f'enum:{english_name}:{column}', 'by': None})
    return found


def meanings_self_check(columns: list[dict], rejected: list[dict], skipped: list[dict], asked: bool = True) -> dict:
    """What ran for a Meanings draft: the counts and the code-side checks. It never says "verified"."""
    drafted = sum(1 for c in columns for v in c['values'] if v['draft'])
    unmeant = sum(len(c['checks']['no_meaning']) for c in columns)
    gone = sum(len(c['checks']['never_seen']) for c in columns)
    confirmed = sum(1 for c in columns if c['confirmed'])
    done, not_done = [], []
    if asked and columns:
        done.append({'key': 'values', 'text': tr('列和取值都在数据里，含义是短文字', 'Columns and codes exist in the data, and the meanings are short texts')})
    if drafted:
        done.append({'key': 'drafted', 'text': tr(f'起草了 {drafted} 个代码的含义', f'Drafted a meaning for {drafted} code(s)')})
    if confirmed:
        done.append({'key': 'confirmed', 'text': tr(f'{confirmed} 列的含义已确认，没有动', f'{confirmed} column(s) already confirmed were left untouched')})
    if unmeant:
        not_done.append({'key': 'unmeant', 'text': tr(f'{unmeant} 个数据里出现的代码还没有含义', f'{unmeant} code(s) in the data still have no meaning')})
    if gone:
        not_done.append({'key': 'gone', 'text': tr(f'{gone} 个已写含义的代码现在的数据里没有', f'{gone} code(s) with a meaning on file do not occur in the data now')})
    if rejected:
        not_done.append({'key': 'rejected', 'text': tr(f'{len(rejected)} 条模型的猜测没通过核对，已剔除', f'{len(rejected)} guess(es) failed the checks and were left out')})
    if skipped:
        not_done.append({'key': 'skipped', 'text': tr(f'{len(skipped)} 列没有起草', f'{len(skipped)} column(s) were not drafted')})
    not_done.append({'key': 'saved', 'text': tr('还没有保存：什么也没有写入', 'Saved: nothing has been written yet')})
    return {'done': done, 'not_done': not_done}

"""What the assistant's cards list as key assumptions and as the self-check, worked out by code from what a draft or a suggestion already contains.
No model is asked and no prompt changes: an assumption is a fact the result stands on (confirmed, with a link to the definition that confirms it) or a question nobody
has answered (open); the self-check names what ran and what did not. An open assumption blocks Apply, and only Apply, until it is answered."""
from __future__ import annotations

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
        done.append({'key': 'checked', 'text': tr(f'数据集和列都存在，{kept} 个主键在全部行上都不重复、没有空值', f'Datasets and columns exist, and each of the {kept} keys is unique and filled on all rows')})
        done.append({'key': 'kept', 'text': tr(f'已存为 {kept} 份模型草稿（还没有提议人）', f'Kept {kept} as model drafts (no proposer yet)')})
        not_done.append({'key': 'confirmed', 'text': tr('还没有人确认：没有一个类型被确认', 'Confirmed: nobody has confirmed any type')})
    if dropped:
        not_done.append({'key': 'dropped', 'text': tr(f'{dropped} 条建议没通过核对，已剔除', f'{dropped} suggestion(s) failed the checks and were left out')})
    return {'done': done, 'not_done': not_done}

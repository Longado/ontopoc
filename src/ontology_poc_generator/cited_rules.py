"""Rules that cite their requirement, and the conflict check (ops/cards/cited-rules.md). No model anywhere: code checks the quotes, the rules and the conflicts.

A citation: any value rule may cite one passage of a confirmed document, with a quote that is word for word in that passage and has at least
document_answers.MIN_QUOTE letters or digits (document_answers.check_quote, the one check answers from documents use; a quote cited twice on one type is
refused, as a repeated quote in an answer is). It is kept in the rule as
{document, passage, quote, sha256}: the document's id, the passage's number within it ("p3"), the quote and the document's file fingerprint when it was cited.
It is part of the rule, so of the type's definition: confirming the type confirms it, and the type reads the document (element_dep). When the document is sent
back, removed or replaced by a new version, a confirmed type that cites it goes to needs another look (document_moved), its readout stops showing the quote
(shown), and it cannot be confirmed again until the citation stands again (problems): the document confirmed with the words the rule was written against.

Who sees what: a person who may not read the cited document (document_answers.may_read) sees the rule and its broken rows without any citation: no name, no
hint that a citation exists; the same in conflict findings, and the type's log gives them no reason for a move a citation caused.

A conflict: two conditional rules on the same type and the same column whose conditions can hold together and whose required values share none, so no value
meets both (value_rules.conflicts). It is a finding, never a block: it is listed on the type's page and in the review queue, with both rules, both quotes and how many rows
meet both conditions now, until one of the rules changes (the pair is identified by both rules as written, citations included) or a note "known: asked <who>"
written by one person is confirmed by another (always a second person, whether or not two-person confirmation is on). The notes are kept in a table of their
own, made when the first one is written, so a workspace without notes is stored as it was."""
from __future__ import annotations

import hashlib
import json

from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_types import (
    TYPE_PREFIX, TypeRefused, _content, _flag, _quote, current_dataset, dataset_columns, element_row, type_id, whole_type_row, _visible)
from ontology_poc_generator.row_rules import keeps, restriction
from ontology_poc_generator.type_access import hidden_columns
from ontology_poc_generator.value_rules import RuleRefused, _trim, columns_of, conflicts, holds_sql, says as rule_says
from ontology_poc_generator.workspace_store import log_line, now_text

MAX_ASKED = 80   # characters of the "asked <who>" of a note: one line
_NOTES = '''CREATE TABLE IF NOT EXISTS rule_conflict_note (
    type TEXT NOT NULL, pair TEXT NOT NULL, asked TEXT NOT NULL, rules_json TEXT NOT NULL, proposed_by TEXT, proposed_by_user_id INTEGER, proposed_at TEXT NOT NULL,
    confirmed_by TEXT, confirmed_by_user_id INTEGER, confirmed_at TEXT, PRIMARY KEY (type, pair))'''


def _docs():
    from ontology_poc_generator import document_answers   # document_answers reads object_types, which reads this module
    return document_answers


# --- a citation -----------------------------------------------------------------------------------------------------------------------------------

def _passage(conn, document: str, passage) -> dict | None:
    return next((p for p in _docs()._passages(conn, document) if p['id'] == passage), None) if isinstance(passage, str) else None


def _removed_name(conn, document: str) -> str | None:
    d = _docs()
    if not d._removed_table(conn):
        return None
    found = conn.execute('SELECT name FROM doc_removed WHERE element_id = ?', (document,)).fetchone()
    return found[0] if found else None


def reader(conn, user: dict | None, kept: list[dict]):
    """The `cite` of value_rules.read_rules for this person: what they wrote ({document, passage, quote}) as it is kept, after code found the quote word for word
    in that passage of a confirmed document they may read. A citation exactly as it is on file (`kept`: the type's rules before this write) whose document is
    not confirmed now is kept as it is, so the type can still be edited; it holds the type back from confirmation until the document stands again (problems).
    Anything else refused: RuleRefused, saying why."""
    d = _docs()
    on_file = [r['cite'] for r in kept if isinstance(r.get('cite'), dict)]

    def cite(given, column: str) -> dict:
        if not isinstance(given, dict):
            raise RuleRefused(tr(f'“{column}”的规则的引用要写成 {{document, passage, quote}}', f'The citation of the rule on "{column}" must be written as {{document, passage, quote}}'))
        document, passage, quote = given.get('document'), given.get('passage'), given.get('quote')
        row = element_row(conn, document) if isinstance(document, str) and document.startswith(d.DOCUMENT_PREFIX) else None
        same = next((c for c in on_file if c['document'] == document and c['passage'] == passage and quote in (None, '', c['quote'])), None)
        if row is None or not d.may_read(conn, user, row):
            if same is not None and row is None:
                return same
            raise RuleRefused(tr(f'“{column}”的规则引用的文档没有：没有这份文档', f'The rule on "{column}" cites a document that is not there: there is no such document'))
        name = _content(row)['name']
        if row['state'] != 'confirmed':
            if same is not None:
                return same
            raise RuleRefused(tr(f'“{column}”的规则引用的《{name}》还没有确认（{d._state_text(row["state"])}）：只能引用确认过的文档', f'The rule on "{column}" cites "{name}", which is not confirmed ({d._state_text(row["state"])}): only a confirmed document can be cited'))
        found = _passage(conn, document, passage)
        if found is None:
            raise RuleRefused(tr(f'“{column}”的规则引用的《{name}》里没有“{passage}”这个段落', f'The rule on "{column}" cites a passage "{passage}" that "{name}" does not have'))
        problem = d.check_quote(quote, found['text'])[0] if isinstance(quote, str) else 'short'
        if problem == 'short':
            raise RuleRefused(tr(f'“{column}”的规则的引用太短：至少要有 {d.MIN_QUOTE} 个字母、汉字或数字', f'The quote of the rule on "{column}" is too short: it needs at least {d.MIN_QUOTE} letters or digits'))
        if problem == 'missing':
            raise RuleRefused(tr(f'“{column}”的规则的引用在《{name}》{found["where"]}的原文里找不到：要一字不差', f'The quote of the rule on "{column}" is not in "{name}", {found["where"]}: it must be word for word'))
        return {'document': document, 'passage': passage, 'quote': quote, 'sha256': _content(row)['sha256']}   # one sentence may justify two rules
    return cite


def _standing(conn, cite: dict) -> tuple[dict | None, dict | None, str | None]:
    """(the document's row, the passage, why the citation does not stand now: None when it stands). It stands while the document is confirmed with the words it
    was cited from (the same file) and the quote is still word for word in that passage."""
    row = element_row(conn, cite['document'])
    if row is None:
        return None, None, tr('文档已移除', 'the document was removed')
    if row['state'] != 'confirmed':
        return row, None, tr('文档被退回或有了新版本，还没有再确认', 'the document was sent back or replaced and is not confirmed again yet')
    found = _passage(conn, cite['document'], cite['passage'])
    if _content(row).get('sha256') != cite.get('sha256') or found is None or _docs().check_quote(cite['quote'], found['text'])[0] is not None:
        return row, None, tr('文档换了新版本，规则是按旧的原话写的：重新引用后保存', 'the document has a new version and the rule quotes the old words: cite it again and save')
    return row, found, None


def shown(conn, user: dict | None, cite: dict) -> dict | None:
    """The citation as this person reads it: the document's name, the passage and where it is, and the quote while it stands; without the quote, saying why, when
    it does not. None (nothing at all) for a person who may not read the document; a removed one is named to builders only."""
    d = _docs()
    row, found, why = _standing(conn, cite)
    if row is None:
        name = _removed_name(conn, cite['document'])
        return {'document': cite['document'], 'passage': cite['passage'], 'name': name, 'stale': why} if name and d._builder(user) else None
    if not d.may_read(conn, user, row):
        return None
    out = {'document': cite['document'], 'passage': cite['passage'], 'name': _content(row)['name']}
    return {**out, 'where': found['where'], 'quote': cite['quote'], **d.check_quote(cite['quote'], found['text'])[1]} if why is None else {**out, 'stale': why}


def readout(conn, user: dict | None, rules: list[dict] | None) -> list[dict] | None:
    """Rules as read (object_types.rules_readout) with each citation as this person may read it, or none."""
    if not rules or not any('cite' in r for r in rules):
        return rules
    out = []
    for r in rules:
        if 'cite' in r:
            seen = shown(conn, user, r['cite'])
            r = {k: v for k, v in r.items() if k != 'cite'}
            if seen is not None:
                r['cite'] = seen
        out.append(r)
    return out


def documents_of(content: dict) -> list[str]:
    """The documents a type's rules cite: what the type reads besides its dataset."""
    return sorted({r['cite']['document'] for r in content.get('rules') or [] if isinstance(r.get('cite'), dict)})


def problems(conn, content: dict) -> list[str]:
    """What holds a type back from confirmation in its citations: each one that does not stand now, by rule and document (read by builders only)."""
    out = []
    names = {p['column']: p['name'] for p in content.get('properties', [])}
    for r in content.get('rules') or []:
        if isinstance(r.get('cite'), dict):
            row, _, why = _standing(conn, r['cite'])
            if why:
                name = _content(row)['name'] if row else (_removed_name(conn, r['cite']['document']) or r['cite']['document'])
                out.append(tr(f'值规则{rule_says(r, names)}：引用的《{name}》不成立了：{why}', f'The value rule {rule_says(r, names)} cites "{name}", which no longer stands: {why}'))
    return out


def moved_reason() -> str:
    """The reason a type stores when a document its rules cite moved: the words every change of a definition shows (object_types.CAUSE_WORDS), so a reader
    who may not read the document learns only that the definition changed, as for any other cause; the type's page shows each citation that no longer stands,
    to whoever may read the document, and the log names it to them."""
    from ontology_poc_generator.object_types import CAUSE_WORDS
    return CAUSE_WORDS['definition']


def document_moved(conn, document: str, how: tuple[str, str], name: str) -> None:
    """Inside the caller's transaction: a document was sent back, removed or replaced (`how`, in both languages). Every confirmed type whose rules cite it goes to
    needs another look (moved_reason); its log line also keeps a reason that names the document, shown to whoever may read it (object_types.log_entries)."""
    readers = [e for (e,) in conn.execute("SELECT element_id FROM element_dep WHERE depends_on = ? AND element_id LIKE 'objtype:%' ORDER BY element_id", (document,))]
    for element_id in readers:
        row = element_row(conn, element_id)
        if row is None or row['state'] != 'confirmed' or document not in documents_of(_content(row)):
            continue
        named = tr(f'值规则引用的《{name}》{how[0]}：引用要再看一遍，再由另一位确认', f'"{name}", cited by a value rule, {how[1]}: the citation needs another look and a second person to confirm it')
        _flag(conn, element_id, moved_reason(), None, [], 'definition', 'self', cites=(document, named))


def may_read_cited(conn, user: dict | None, document: str) -> bool:
    """Whether this person may read the document a citation names: one they may read, or (a builder) one since removed."""
    d = _docs()
    row = element_row(conn, document)
    return d.may_read(conn, user, row) or (row is None and d._builder(user))


# --- conflicts --------------------------------------------------------------------------------------------------------------------------------------

def pair_key(a: dict, b: dict) -> str:
    """The pair of rules as anyone who reads them is shown them: without their citations, which a reader may not be allowed to know of. (A note is about the
    rules as written, citations included: _notes matches them whole.)"""
    both = sorted(json.dumps({k: v for k, v in r.items() if k != 'cite'}, ensure_ascii=False, sort_keys=True) for r in (a, b))
    return hashlib.sha256(json.dumps(both, ensure_ascii=False).encode()).hexdigest()[:16]


def _notes_table(conn) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'rule_conflict_note'").fetchone() is not None


def _notes(conn, english: str, rules: list[dict] | None = None) -> dict[str, dict]:
    """{pair key: note} of a type's notes; with `rules` (the type's rules now), only the notes whose two rules are exactly two of them, citations included."""
    if not _notes_table(conn):
        return {}
    cursor = conn.execute('SELECT * FROM rule_conflict_note WHERE type = ?', (english,))
    names = [c[0] for c in cursor.description]
    notes = {r[1]: dict(zip(names, r)) for r in cursor}
    if rules is not None:
        now = [json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rules]
        notes = {k: n for k, n in notes.items() if all(json.dumps(r, ensure_ascii=False, sort_keys=True) in now for r in json.loads(n['rules_json']))}
    return notes


def drop_stale_notes(conn, english: str, content: dict, who: str | None) -> None:
    """Inside the caller's transaction, once a type's rules changed: every note whose two rules are not both among them now is deleted, so changing a rule back
    does not bring a note back (it was about the pair as it was confirmed). The type's log says so."""
    kept = _notes(conn, english, content.get('rules') or [])
    for key, note in _notes(conn, english).items():
        if key not in kept:
            conn.execute('DELETE FROM rule_conflict_note WHERE type = ? AND pair = ?', (english, key))
            log_line(conn, who or tr('未署名', 'unsigned'), type_id(english), 'conflict_note_dropped', after={'key': key, 'asked': note['asked']})


def _own_rows(conn, dataset: dict, limit) -> str:
    """A temporary list of the rowids a row rule lets this person see (as object_types.rules_readout makes it); its name."""
    cursor = conn.execute(f'SELECT rowid, * FROM {_quote(dataset["table_name"])} ORDER BY rowid')
    names = [c[0] for c in cursor.description][1:]
    kept = [(r[0],) for r in cursor if keeps(dict(zip(names, r[1:])), limit)]
    conn.execute('DROP TABLE IF EXISTS temp.conflict_rows')
    conn.execute('CREATE TEMP TABLE conflict_rows (r INTEGER PRIMARY KEY)')
    conn.executemany('INSERT INTO temp.conflict_rows VALUES (?)', kept)
    return 'conflict_rows'


def _overlap(conn, dataset: dict, merged: list[dict], only: str | None) -> int:
    holds, params = holds_sql(merged, lambda c: (_trim(_quote(c)), _quote(c)))
    within = f' AND rowid IN (SELECT r FROM temp.{only})' if only else ''
    return conn.execute(f'SELECT COUNT(*) FROM {_quote(dataset["table_name"])} WHERE {holds}{within}', params).fetchone()[0]


def _may_confirm_note(note: dict, user: dict | None, who: str | None) -> bool:
    """A note is confirmed by someone other than whoever wrote it, always (two-person confirmation on or off), and by a builder or an admin."""
    if user is not None and user.get('role') not in ('builder', 'admin'):
        return False
    person = user.get('id') if user else None
    if person is not None and note['proposed_by_user_id'] is not None:
        return person != note['proposed_by_user_id']
    return (who or (user or {}).get('display_name')) != note['proposed_by']


def _note_view(note: dict | None, user: dict | None) -> dict | None:
    if note is None:
        return None
    can = _may_confirm_note(note, user, None)
    builder = user is None or user.get('role') in ('builder', 'admin')   # the sentence on who may confirm it is for those who could
    return {'asked': note['asked'], 'proposed_by': note['proposed_by'], 'proposed_at': note['proposed_at'], 'state': 'checked', 'may_confirm': can,
            **({} if can or not builder else {'held': tr('记下这条的人不能自己确认：要另一位来确认', 'Whoever wrote the note cannot confirm it: a second person must')})}


def findings(conn, element_id: str, content: dict, user: dict | None, count: bool = True) -> list[dict]:
    """The conflicts among a type's rules as this person may read them: none on a column kept from them, each rule's citation as they may read it, and (`count`)
    how many rows meet both conditions now, of the rows a row rule lets them see. A pair whose "known" note is confirmed is not listed."""
    rules = content.get('rules') or []
    pairs = conflicts(rules)
    if not pairs:
        return []
    hidden = hidden_columns(conn, element_id, user)
    notes = _notes(conn, content['english_name'], rules)
    names = {p['column']: p['name'] for p in content['properties']}
    dataset = current_dataset(conn, content['dataset']) if count else None
    cols = dataset_columns(conn, dataset['id']) if dataset else {}
    limit = restriction(conn, element_id, user) if dataset else None
    only = None
    out = []
    try:
        for i, j, merged in pairs:
            a, b = rules[i], rules[j]
            if (columns_of(a) | columns_of(b)) & hidden:
                continue
            key = pair_key(a, b)
            note = notes.get(key)
            if note is not None and note['confirmed_at']:
                continue
            rows = None
            if dataset is not None and all(c['column'] in cols for c in merged):
                if limit is not None and only is None:
                    only = _own_rows(conn, dataset, limit)
                rows = _overlap(conn, dataset, merged, only)
            where = tr('、'.join(f'“{names.get(c["column"], c["column"])}”是 {c["equals"]}' for c in merged), ' and '.join(f'"{names.get(c["column"], c["column"])}" is {c["equals"]}' for c in merged))
            column = names.get(a['column'], a['column'])
            values = lambda r: tr('、'.join(r['one_of']), ', '.join(r['one_of'])) if 'one_of' in r else r['equals']
            says = tr(f'两条值规则冲突：当{where} 时，一条要求“{column}”是 {values(a)}，另一条要求是 {values(b)}',
                      f'Two value rules disagree: when {where}, one requires "{column}" to be {values(a)} and the other {values(b)}')
            both = readout(conn, user, [{'index': i, 'says': rule_says(a, names), **({'cite': a['cite']} if 'cite' in a else {})},
                                        {'index': j, 'says': rule_says(b, names), **({'cite': b['cite']} if 'cite' in b else {})}])
            out.append({'key': key, 'column': a['column'], 'name': column, 'rules': both, 'when': merged, 'rows': rows, 'says': says, 'note': _note_view(note, user)})
    finally:
        if only:
            conn.execute(f'DROP TABLE IF EXISTS temp.{only}')
    return out


def _finding(conn, payload: dict, user: dict | None) -> tuple[dict, dict, dict]:
    row = whole_type_row(conn, payload.get('id'), user)
    content = _content(row)
    key = payload.get('key')
    found = next((f for f in findings(conn, row['element_id'], content, user, count=False) if f['key'] == key), None)
    if found is None:
        raise TypeRefused(tr('没有这条冲突：规则可能已经改了，请刷新', 'There is no such conflict: a rule may have changed. Refresh'), 404)
    return row, content, found


def record_note(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """POST /api/workspace/types/conflict-note {id, key, asked}: "known: asked <who>" on one conflict, written by this person and waiting for a second one. Writing
    it again before it is confirmed replaces it (the new writer is then the one who cannot confirm it)."""
    if user is not None and user.get('role') not in ('builder', 'admin'):
        raise TypeRefused(tr('记下冲突要搭建者', 'Noting a conflict needs a builder'), 403)
    asked = payload.get('asked')
    asked = asked.strip() if isinstance(asked, str) else ''
    if not asked or len(asked) > MAX_ASKED or '\n' in asked or '\r' in asked:
        raise TypeRefused(tr(f'要写问过谁：1 到 {MAX_ASKED} 个字，不能换行', f'Say who was asked: 1 to {MAX_ASKED} characters, on one line'))
    row, content, found = _finding(conn, payload, user)
    rules = content['rules']
    pair = [rules[found['rules'][0]['index']], rules[found['rules'][1]['index']]]
    conn.execute(_NOTES)
    conn.execute('BEGIN IMMEDIATE')
    try:
        if conn.execute('SELECT 1 FROM rule_conflict_note WHERE type = ? AND pair = ? AND confirmed_at IS NOT NULL', (content['english_name'], found['key'])).fetchone():
            raise TypeRefused(tr('这条已经确认过了', 'Already confirmed'), 409)
        conn.execute('INSERT OR REPLACE INTO rule_conflict_note(type, pair, asked, rules_json, proposed_by, proposed_by_user_id, proposed_at) VALUES (?, ?, ?, ?, ?, ?, ?)',
                     (content['english_name'], found['key'], asked, json.dumps(pair, ensure_ascii=False, sort_keys=True), who, (user or {}).get('id'), now_text()))
        log_line(conn, who or tr('未署名', 'unsigned'), row['element_id'], 'conflict_note', after={'key': found['key'], 'asked': asked, 'state': 'checked'})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return {'conflicts': findings(conn, row['element_id'], content, user)}


def confirm_note(conn, payload: dict, who: str | None, user: dict | None) -> dict:
    """POST /api/workspace/types/conflict-note/confirm {id, key}: a second person confirms the note; the conflict is no longer listed."""
    row, content, found = _finding(conn, payload, user)
    note = _notes(conn, content['english_name'], content['rules']).get(found['key'])
    if note is None:
        raise TypeRefused(tr('这条冲突还没有人记下“已知”', 'Nobody has noted this conflict as known yet'), 404)
    if not _may_confirm_note(note, user, who):
        raise TypeRefused(tr('这条是你自己记下的，要另一位来确认', 'You wrote this note yourself, so someone else must confirm it'), 403)
    conn.execute('BEGIN IMMEDIATE')
    try:
        if conn.execute('UPDATE rule_conflict_note SET confirmed_by = ?, confirmed_by_user_id = ?, confirmed_at = ? WHERE type = ? AND pair = ? AND confirmed_at IS NULL AND asked = ?',
                        (who, (user or {}).get('id'), now_text(), content['english_name'], found['key'], note['asked'])).rowcount != 1:
            raise TypeRefused(tr('这条在你看过之后变了，请刷新后再看', 'It changed after you looked. Refresh and look again'), 409)
        log_line(conn, who or tr('未署名', 'unsigned'), row['element_id'], 'conflict_note_confirmed', after={'key': found['key'], 'asked': note['asked'], 'proposed_by': note['proposed_by']})
        conn.execute('COMMIT')
    except BaseException:
        conn.execute('ROLLBACK')
        raise
    return {'conflicts': findings(conn, row['element_id'], content, user)}


def queue_items(conn, user: dict | None, light: bool) -> list[dict]:
    """One review-queue item per conflict this person may see on a type they may see: the finding (with the row count unless `light`, and only for a person no
    row rule limits: the type's page counts their own rows). It can be confirmed when a note waits that they did not write."""
    items = []
    for (element_id,) in conn.execute("SELECT element_id FROM element_state WHERE element_id LIKE 'objtype:%' AND json_extract(content_json, '$.rules') IS NOT NULL ORDER BY element_id").fetchall():
        row = element_row(conn, element_id)
        if not _visible(conn, row, user):
            continue
        content = _content(row)
        if not conflicts(content.get('rules') or []):
            continue
        for f in findings(conn, element_id, content, user, count=not light and restriction(conn, element_id, user) is None):
            note = f['note']
            lines = [{'ok': False, 'text': f['says'] + (tr(f'：现在有 {f["rows"]} 行同时满足两条的条件', f': {f["rows"]} rows meet both conditions now') if f['rows'] is not None else '')}]
            for r in f['rules']:
                c = r.get('cite')
                lines.append({'ok': True, 'text': r['says'] + (tr(f'——依据《{c["name"]}》{c["where"]}：“{c["quote"]}”', f' — from "{c["name"]}", {c["where"]}: "{c["quote"]}"') if c and 'quote' in c else '')})
            if note:
                lines.append({'ok': True, 'text': tr(f'已知：问过 {note["asked"]}（{note["proposed_by"]} 记下，等另一位确认）', f'Known: asked {note["asked"]} (noted by {note["proposed_by"]}, waiting for a second person to confirm)')})
            items.append({'element': f'conflict:{content["english_name"]}:{f["key"]}', 'kind': 'conflict', 'title': content['name'], 'id': content['english_name'], 'key': f['key'],
                          'state': 'pending', 'version': None, 'can_confirm': bool(note and note['may_confirm']), 'lines': [] if light else lines, 'conflict': f,
                          'proposed_by': note['proposed_by'] if note else None, 'written_at': note['proposed_at'] if note else None})
    return items

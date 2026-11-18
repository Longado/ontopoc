"""The assistant's Meanings mode: a model drafts what the codes of one workspace object type's code columns mean. One bounded call (code_meanings.draft_meanings
over the counts and facts code works out from the type's current dataset version, never a row); the draft is cleaned and checked by code and sent back with the
facts a person decides from. Nothing is saved here: Apply is the page sending the kept columns through the ordinary meanings path (object_types.propose_meanings),
so every existing check runs there. A column whose meanings are already confirmed is not drafted and never changes."""
from __future__ import annotations

from ontology_poc_generator.assistant_checks import meanings_assumptions, meanings_self_check
from ontology_poc_generator.code_meanings import code_columns, draft_meanings
from ontology_poc_generator.lang import tr
from ontology_poc_generator.object_types import (
    TypeRefused, _content, _kept_meanings, dataset_columns, element_row, enum_id, refuse_if_limited, whole_type_row)
from ontology_poc_generator.type_access import hidden_values
from ontology_poc_generator.workspace_store import current_dataset, dataset_records

MODEL_SECONDS = 60   # one call, and it sees counts only


def _order(value: str):
    return (0, int(value), value) if value.lstrip('-').isdigit() else (1, 0, value)


def draft_type_meanings(conn, gateway, english_name, user: dict | None) -> dict:
    """{'type', 'dataset', 'version', 'model', 'columns': [...], 'rejected', 'skipped', 'assumptions', 'self_check'}. TypeRefused for a type this person may not edit
    (404 not theirs to see; 403 a property or rows kept from them), for a type with no code columns (400) and for a model that failed (502). Each column carries its
    values with the draft beside what is on file, and `checks`: codes in the data with no meaning, meanings for codes that never occur, and whether it is confirmed."""
    row = whole_type_row(conn, english_name, user)   # the "properties you cannot see" rule: a person kept from any column does not write this type's meanings
    refuse_if_limited(conn, row, user)               # nor one who cannot see all the rows the counts are over
    content = _content(row)
    dataset = current_dataset(conn, content['dataset'])
    if dataset is None:
        raise TypeRefused(tr(f'数据集“{content["dataset"]}”已经不在了', f'The dataset "{content["dataset"]}" is gone'), 409)
    wanted = [p['column'] for p in content['properties'] if p['enum']]
    if not wanted:
        raise TypeRefused(tr('这个对象类型没有代码列，没有含义可写', 'This object type has no code columns, so there are no meanings to draft'))
    cols = dataset_columns(conn, dataset['id'])
    source = content['dataset']
    bundle = {'sources': {source: {'records': dataset_records(conn, dataset)}}}
    profiles = {p['column']: p for p in code_columns(bundle, skip=frozenset((source, c) for c in content['key']))}
    unsent = hidden_values(conn, row['element_id'])
    state_of = {c: (element_row(conn, enum_id(content['english_name'], c)) or {}).get('state') for c in wanted}
    skipped, to_ask = [], []
    for column in wanted:
        if column not in cols:
            skipped.append({'column': column, 'reason': tr('数据集里已经没有这一列', 'the dataset no longer has this column')})
        elif column not in profiles:
            skipped.append({'column': column, 'reason': tr('取值看不出是代码（太多、太长，或是年份、是/否）', 'its values do not look like codes (too many, too long, or years or yes/no)')})
        elif column in unsent:
            skipped.append({'column': column, 'reason': tr('这一列标了不发送给模型', 'this column is marked not to be sent to the model')})
        elif state_of[column] != 'confirmed':
            to_ask.append(profiles[column])
    drafted = {'columns': {}, 'rejected': [], 'model': None}
    if to_ask:   # every column confirmed: nothing to ask
        drafted = draft_meanings(to_ask, gateway, content.get('description') or content['name'], timeout_seconds=MODEL_SECONDS)
        if drafted['error']:
            raise TypeRefused(drafted['error'], 502)
    out = []
    for column in wanted:
        if column not in profiles or column in unsent:
            continue
        profile, confirmed = profiles[column], state_of[column] == 'confirmed'
        on_file = {e['value']: e for e in _kept_meanings(conn, content['english_name'], column)}
        guesses = {} if confirmed else drafted['columns'].get(profile['id'], {})   # confirmed meanings are never in the draft
        seen = {v['value'] for v in profile['values']}
        values = [{'value': v['value'], 'rows': v['rows'], 'facts': v['facts'], 'pattern': v['pattern'], 'current': on_file[v['value']]['label'] if v['value'] in on_file else '',
                   'draft': guesses.get(v['value'])} for v in sorted(profile['values'], key=lambda v: _order(v['value']))]
        out.append({'column': column, 'field': profile['field'], 'rows': profile['rows'], 'state': state_of[column], 'confirmed': confirmed, 'values': values,
                    'checks': {'confirmed': confirmed,
                               'no_meaning': [x['value'] for x in values if not x['current'] and not x['draft']],   # in the data, with no meaning on file or drafted
                               'never_seen': sorted((v for v in on_file if v not in seen), key=_order)}})   # a meaning on file for a code the data does not have now
    body = {'type': content['english_name'], 'dataset': source, 'version': dataset['version'], 'model': drafted['model'], 'columns': out, 'rejected': drafted['rejected'], 'skipped': skipped}
    return {**body, 'assumptions': meanings_assumptions(content['english_name'], out), 'self_check': meanings_self_check(out, drafted['rejected'], skipped, asked=bool(to_ask))}

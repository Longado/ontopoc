"""What changed between two versions of a client's file: per object, how many there were, and which came and went."""
from __future__ import annotations

from ontology_poc_generator.object_rows import _labeller, node_id
from ontology_poc_generator.ontology_compare import match_types
from ontology_poc_generator.public_ontology import build_graph, normalize_proposal

EXAMPLES = 5


def version_diff(previous: dict, previous_bundle: dict, result: dict, bundle: dict) -> dict:
    before_graph, after_graph = build_graph(previous['ontology'], previous_bundle), build_graph(result['ontology'], bundle)
    before_types = {t['key']: t for t in normalize_proposal(previous['ontology'])['object_types']}
    after_types = {t['key']: t for t in normalize_proposal(result['ontology'])['object_types']}
    # the model names objects afresh on every build (Chicago's vendors: `vendor`, then `supplier`); the same table and
    # identity fields make them the same object, as the comparison with a reference already decides
    matched = {after: before for before, after in match_types(list(before_types.values()), list(after_types.values())).items()}
    pairs = [(matched.get(k), k) for k in after_types] + [(k, None) for k in before_types if k not in matched.values()]
    value = lambda inst: node_id(inst).split(':', 1)[1]
    objects = []
    for before_key, after_key in pairs:
        before = {value(i): i for i in before_graph['records_of'] if i[0] == before_key}
        after = {value(i): i for i in after_graph['records_of'] if i[0] == after_key}
        added = [i for n, i in after.items() if n not in before]
        removed = [i for n, i in before.items() if n not in after]
        name_after = _labeller(after_types[after_key], bundle, after_graph['records_of']) if after_key else None
        name_before = _labeller(before_types[before_key], previous_bundle, before_graph['records_of']) if before_key else None
        t = after_types.get(after_key) or before_types[before_key]
        objects.append({'type': after_key or before_key, 'label': t.get('label') or t['key'],
                        'before': len(before), 'after': len(after), 'added': len(added), 'removed': len(removed),
                        'added_examples': [name_after(i)[0] for i in added[:EXAMPLES]] if name_after else [],
                        'removed_examples': [name_before(i)[0] for i in removed[:EXAMPLES]] if name_before else []})
    return {'previous': previous['saved_as'], 'previous_started_at': previous.get('started_at'), 'objects': objects}

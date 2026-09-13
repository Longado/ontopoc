# Superseded by src/ontology_poc_generator/public_ontology.py and public_scope.py; kept as the 2026-09-13 spike record.
"""Spike: auto-build an ontology from NHTSA data, verify it in code, answer a recall scope question."""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.environ['ONTOPOC_SRC'])
from ontology_poc_generator.model_gateway import OpenAICompatibleGateway  # noqa: E402

import ontology as o  # noqa: E402
import prompts as p  # noqa: E402

OUT = Path(__file__).parent / 'out'
MODEL = 'deepseek-flash'
BATCH = 20  # complaints per matcher call; keeps one response well inside the output limit


def call(gw, system, user, log, tag):
    c = gw.complete_json(system_prompt=system, user_prompt=user)
    log.append({'tag': tag, 'model': c.model, 'at': datetime.now(timezone.utc).isoformat()})
    return json.loads(c.content), c.model


def texts(spec, g, sources, inst):
    """Long string attributes of every record the instance appears in (spec-declared attributes only)."""
    t = next(t for t in spec['object_types'] if t['key'] == inst[0])
    out = []
    for (src, i), by_type in g['per_record'].items():
        if inst in by_type.get(inst[0], []):
            for a in t.get('attributes') or []:
                if a.get('source') == src:
                    out += [str(v) for v in o.resolve(sources[src][i], a['path']) if isinstance(v, str) and len(v) > 40]
    return list(dict.fromkeys(out))


def main():
    OUT.mkdir(exist_ok=True)
    gw = OpenAICompatibleGateway(api_base='https://api.deepseek.com', api_key=os.environ['DEEPSEEK_API_KEY'],
                                 model=MODEL, timeout_seconds=180)
    sources, log = o.load_sources(), []
    catalog = o.field_catalog(sources)
    decision = ('一次汽车召回发布后，判断：哪些车型年款在召回范围内；哪些车主投诉指向同一部件，'
                '其中哪些车辆不在任何同部件召回的范围里（范围外疑似同类问题，需要质量工程师复核）。')
    user = json.dumps({'decision': decision, 'sources': catalog}, ensure_ascii=False)
    attempts, feedback, prev = [], None, None
    while True:  # retry only while the error list keeps shrinking (no-progress stop)
        msg = user if feedback is None else json.dumps(
            {'decision': decision, 'sources': catalog, 'previous_spec': attempts[-1]['spec'],
             'errors_found_by_code': feedback}, ensure_ascii=False)
        spec, model = call(gw, p.MODELER_SYSTEM, msg, log, f'modeler#{len(attempts) + 1}')
        errors = o.validate_spec(spec, sources)
        metrics = None
        if not errors:
            g = o.build_graph(spec, sources)
            metrics, errors = o.graph_checks(spec, sources, g)
        attempts.append({'spec': spec, 'errors': errors, 'metrics': metrics})
        print(f'modeler attempt {len(attempts)}: {len(errors)} errors', flush=True)
        if not errors or (prev is not None and len(errors) >= prev):
            break
        prev, feedback = len(errors), errors
    (OUT / 'ontology_attempts.json').write_text(json.dumps(attempts, ensure_ascii=False, indent=2, default=str))
    if errors:
        print('auto-build failed; see out/ontology_attempts.json')
        return 1
    role = {t['role']: t['key'] for t in spec['object_types']}
    results = {}
    for campaign in sys.argv[1:]:
        ev = next(i for i in g['inst_sources'] if i[0] == role['event'] and i[1][0][1] == campaign)
        sc = o.scope(spec, g, ev)
        recall_text = '\n'.join(texts(spec, g, sources, ev))
        cands = sc['candidates']
        verdicts = {}
        for n in range(0, len(cands), BATCH):
            batch = cands[n:n + BATCH]
            items = [{'id': str(c['signal'][1][0][1]), 'text': ' '.join(texts(spec, g, sources, c['signal']))}
                     for c in batch]
            out, _ = call(gw, p.MATCHER_SYSTEM, json.dumps({'recall_defect': recall_text, 'complaints': items},
                                                           ensure_ascii=False), log, f'matcher:{campaign}#{n // BATCH}')
            by_id = {r.get('id'): r for r in out.get('results', []) if isinstance(r, dict)}
            for it in items:
                r = by_id.get(it['id'])
                if r is None or r.get('verdict') not in ('yes', 'no', 'unknown'):
                    verdicts[it['id']] = {'verdict': 'unknown', 'reasoning': 'model returned no valid result', 'evidence': ''}
                elif r['verdict'] == 'yes' and (not r.get('evidence') or r['evidence'] not in it['text']):
                    verdicts[it['id']] = {**r, 'verdict': 'unknown', 'reasoning': 'evidence not found in complaint text'}
                else:
                    verdicts[it['id']] = r
            print(f'{campaign}: matched {min(n + BATCH, len(cands))}/{len(cands)}', flush=True)
        for c in cands:
            c['text_check'] = verdicts[str(c['signal'][1][0][1])]
        results[campaign] = sc
    report = {'model': MODEL, 'prompt_versions': [p.MODELER_VERSION, p.MATCHER_VERSION], 'calls': log,
              'spec': spec, 'metrics': attempts[-1]['metrics'], 'part_of': sorted(g['part_of']),
              'scopes': results}
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    print('done: out/report.json')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

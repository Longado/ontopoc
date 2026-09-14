"""Rerun the model's first-pass verdicts on the exact inputs of a recorded run and count how many change."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.nhtsa_sources import PublicSourceError, load_source_bundle
from ontology_poc_generator.public_scope import MATCHER_PROMPT_VERSION, ScopeError, check_candidates, require_matching_bundle


def _cid(candidate: dict) -> str:
    return '|'.join(str(v) for v in candidate['signal'].values())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True, help='a recorded online run (examples/nhtsa/runs/...)')
    parser.add_argument('--snapshot', type=Path, required=True, help='the snapshot that run was built from')
    parser.add_argument('--campaign', action='append', help='repeatable; default: every campaign the run checked')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default=os.environ.get('EIP_MODEL_NAME', 'deepseek-flash'))
    args = parser.parse_args(argv)
    key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('EIP_MODEL_API_KEY')
    if not key:
        print('blocked: configure DEEPSEEK_API_KEY or EIP_MODEL_API_KEY locally', file=sys.stderr)
        return 2
    if args.output.exists():
        print('output already exists; choose a new path', file=sys.stderr)
        return 2
    try:
        report = json.loads(args.report.read_text(encoding='utf-8'))
        bundle = load_source_bundle(args.snapshot)
        require_matching_bundle(report['ontology'], bundle)
    except (OSError, ValueError, KeyError, PublicSourceError, ScopeError) as exc:
        print(f'input error: {exc}', file=sys.stderr)
        return 2
    campaigns = args.campaign or list(report['scopes'])
    missing = [c for c in campaigns if c not in report['scopes']]
    if missing:
        print(f'not in the recorded run: {", ".join(missing)}', file=sys.stderr)
        return 2
    gateway = OpenAICompatibleGateway(api_base='https://api.deepseek.com', api_key=key,
                                     model=args.model, timeout_seconds=180, temperature=0)
    result = {'schema': 'model_stability.v1', 'report': args.report.name, 'snapshot': args.snapshot.name,
              'model': args.model, 'prompt_version': MATCHER_PROMPT_VERSION,
              'started_at': datetime.now(timezone.utc).isoformat(), 'campaigns': {}}
    for campaign in campaigns:
        recorded = report['scopes'][campaign]
        print(f'{campaign}: rechecking {len(recorded["candidates"])} candidates ...', flush=True)
        bare = {**recorded, 'candidates': [{k: v for k, v in c.items() if k != 'text_check'} for c in recorded['candidates']]}
        again = {_cid(c): c['text_check']['verdict'] for c in check_candidates(bare, report['ontology'], bundle, gateway)['candidates']}
        before = {_cid(c): c['text_check']['verdict'] for c in recorded['candidates']}
        changed = [{'id': i, 'before': v, 'after': again[i]} for i, v in before.items() if again[i] != v]
        result['campaigns'][campaign] = {'candidates': len(before), 'same': len(before) - len(changed), 'changed': changed}
    result['totals'] = {k: sum(c[k] if k != 'changed' else len(c[k]) for c in result['campaigns'].values())
                        for k in ('candidates', 'same', 'changed')}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    totals = result['totals']
    print(f'{totals["changed"]} of {totals["candidates"]} first calls changed on the same inputs')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

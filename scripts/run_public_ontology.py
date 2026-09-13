"""Online run: auto-build the ontology for a public snapshot, then check recall scope per campaign."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.nhtsa_sources import PublicSourceError, bundle_content_hash, load_source_bundle
from ontology_poc_generator.public_ontology import auto_build_ontology
from ontology_poc_generator.public_scope import ScopeError, check_candidates, scope

DEFAULT_SNAPSHOT = Path(__file__).resolve().parents[1] / 'examples/nhtsa/chevrolet_bolt_2017_2023.json'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', type=Path, default=DEFAULT_SNAPSHOT)
    parser.add_argument('--campaign', action='append', required=True, help='recall campaign number; repeatable')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default=os.environ.get('EIP_MODEL_NAME', 'deepseek-flash'))
    args = parser.parse_args(argv)
    key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('EIP_MODEL_API_KEY')
    if not key:
        print('blocked: configure DEEPSEEK_API_KEY or EIP_MODEL_API_KEY locally', file=sys.stderr)
        return 2
    if args.output.exists():
        print('output already exists; choose a new report path', file=sys.stderr)
        return 2
    try:
        bundle = load_source_bundle(args.snapshot)
    except PublicSourceError as exc:
        print(f'input error: {exc}', file=sys.stderr)
        return 2
    gateway = OpenAICompatibleGateway(api_base='https://api.deepseek.com', api_key=key,
                                     model=args.model, timeout_seconds=180)
    report = {'schema': 'public_ontology_run.v1', 'online': True, 'requested_model': args.model,
              'snapshot': args.snapshot.name, 'source_bundle_hash': bundle_content_hash(bundle),
              'started_at': datetime.now(timezone.utc).isoformat(), 'ontology': None, 'scopes': {},
              'errors': [], 'finished': False,
              'boundary': 'Candidates for quality review only; no recall, defect or disposition is confirmed.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)

    def save():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print('building ontology ...', flush=True)
    report['ontology'] = ontology = auto_build_ontology(bundle, gateway)
    save()
    print(f'ontology: {ontology["status"]} after {len(ontology["attempts"])} attempt(s)', flush=True)
    if ontology['status'] != 'auto_built_verified':
        report['errors'].append('ontology blocked; see ontology.verification.errors')
        save()
        return 1
    for campaign in args.campaign:
        try:
            result = scope(ontology, bundle, {'campaign_number': campaign})
        except ScopeError as exc:
            report['errors'].append(f'{campaign}: {exc}')
            save()
            continue
        print(f'{campaign}: {len(result["candidates"])} candidates, checking text ...', flush=True)
        report['scopes'][campaign] = check_candidates(result, ontology, bundle, gateway)
        save()
    report['finished'] = True
    save()
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())

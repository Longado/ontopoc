"""Explicit online extraction benchmark; sends only the five public FDA records."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.recognition import RecognitionError
from ontology_poc_generator.recall_extraction import extract_record
from ontology_poc_generator.recall_scope import load_catalog


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default=os.environ.get('EIP_MODEL_NAME', 'deepseek-flash'))
    args = parser.parse_args(argv)
    key = os.environ.get('DEEPSEEK_API_KEY') or os.environ.get('EIP_MODEL_API_KEY')
    if not key:
        print('blocked: configure DEEPSEEK_API_KEY or EIP_MODEL_API_KEY locally', file=sys.stderr)
        return 2
    if not args.model.startswith('deepseek-'):
        print('input error: this benchmark requires a DeepSeek model', file=sys.stderr)
        return 2
    if args.output.exists():
        print('output already exists; choose a new report path', file=sys.stderr)
        return 2
    catalog = load_catalog()
    gateway = OpenAICompatibleGateway(api_base='https://api.deepseek.com', api_key=key,
                                     model=args.model, timeout_seconds=60)
    report = {'schema': 'public_recall_extraction_check.v1', 'online': True,
              'requested_model': args.model, 'source_url': catalog['source_url'],
              'source_retrieved_at': catalog['retrieved_at'],
              'started_at': datetime.now(timezone.utc).isoformat(), 'results': [],
              'boundary': 'Source extraction comparison only; no recall prediction or business action.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for recall_number in sorted(catalog['records']):
        try:
            result = extract_record(catalog, recall_number, gateway)
        except RecognitionError as exc:
            result = {'recall_number': recall_number, 'accepted': False, 'error': str(exc)}
        report['results'].append(result)
        report['accepted_count'] = sum(r['accepted'] for r in report['results'])
        report['completed_count'] = len(report['results'])
        report['finished'] = len(report['results']) == len(catalog['records'])
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f"{recall_number}: {'accepted' if result['accepted'] else 'rejected/error'}", flush=True)
    return 0 if all(r['accepted'] for r in report['results']) else 1


if __name__ == '__main__':
    raise SystemExit(main())

"""Build and evaluate a company ontology from a business file, the same way the upload page does."""
import argparse
import json
from pathlib import Path
import sys

from ontology_poc_generator.company_ontology import build_and_evaluate
from ontology_poc_generator.company_sources import SourceFileError, load_table_file
from ontology_poc_generator.ontology_server import gateway_from_env


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--file', type=Path, required=True, help='CSV or Excel (.xlsx)')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--purpose', help='one line on what the ontology should let people answer (optional)')
    args = parser.parse_args(argv)
    gateway = gateway_from_env()
    if gateway is None:
        print('blocked: configure DEEPSEEK_API_KEY or EIP_MODEL_API_KEY locally', file=sys.stderr)
        return 2
    if args.output.exists():
        print('output already exists; choose a new path', file=sys.stderr)
        return 2
    try:
        bundle = load_table_file(args.file.name, args.file.read_bytes(), args.purpose)
    except (OSError, SourceFileError) as exc:
        print(f'input error: {exc}', file=sys.stderr)
        return 2
    result = build_and_evaluate(bundle, gateway)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    ontology = result['ontology']
    print(f'{ontology["status"]} after {len(ontology["attempts"])} attempt(s): '
          f'{len(ontology["object_types"])} object types, {len(ontology["relations"])} relations')
    return 0 if ontology['status'] == 'auto_built_verified' else 1


if __name__ == '__main__':
    raise SystemExit(main())

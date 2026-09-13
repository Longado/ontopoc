"""Fetch NHTSA recalls and complaints for one make, models and model years into a public source bundle."""
import argparse
import json
from pathlib import Path
import sys

from ontology_poc_generator.nhtsa_sources import RECALL_SCOPE_DECISION, PublicSourceError, fetch_nhtsa_bundle


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--make', required=True)
    parser.add_argument('--model', action='append', required=True, help='repeatable, e.g. "bolt ev"')
    parser.add_argument('--years', required=True, help='single year or range, e.g. 2017-2023')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    first, _, last = args.years.partition('-')
    years = list(range(int(first), int(last or first) + 1))
    if args.output.exists():
        print('output already exists; choose a new snapshot path', file=sys.stderr)
        return 2
    try:
        bundle = fetch_nhtsa_bundle(args.make, args.model, years, decision=RECALL_SCOPE_DECISION)
    except PublicSourceError as exc:
        print(f'fetch failed: {exc}', file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'wrote {sum(len(s["records"]) for s in bundle["sources"].values())} records to {args.output.name}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

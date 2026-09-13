"""Build (or --check) the static review-page data from a recorded online run and its snapshot."""
import argparse
import json
from pathlib import Path
import sys

from ontology_poc_generator.nhtsa_sources import PublicSourceError, load_source_bundle
from ontology_poc_generator.public_review_pack import PackError, build_review_pack

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, default=ROOT / 'examples/nhtsa/runs/2026-09-13-deepseek-flash.json')
    parser.add_argument('--snapshot', type=Path, default=ROOT / 'examples/nhtsa/chevrolet_bolt_2017_2023.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'landing-page/public/data/nhtsa-bolt-review-pack.json')
    parser.add_argument('--check', action='store_true', help='fail if the output is missing or stale')
    args = parser.parse_args(argv)
    try:
        pack = build_review_pack(json.loads(args.report.read_text(encoding='utf-8')), load_source_bundle(args.snapshot))
    except (OSError, ValueError, PackError, PublicSourceError) as exc:
        print(f'cannot build review pack: {exc}', file=sys.stderr)
        return 2
    text = json.dumps(pack, ensure_ascii=False, separators=(',', ':')) + '\n'
    if args.check:
        current = args.output.read_text(encoding='utf-8') if args.output.exists() else None
        if current != text:
            print(f'{args.output.name} is stale; rerun without --check', file=sys.stderr)
            return 1
        print(f'{args.output.name} is up to date')
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text, encoding='utf-8')
    print(f'wrote {args.output.name}: {len(pack["recalls"])} recalls')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

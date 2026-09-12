import argparse
import json
import sys

from ontology_poc_generator.recall_scope import DEFAULT_CATALOG, load_catalog, match_recall


def main(argv=None):
    parser = argparse.ArgumentParser(description='核对公开召回事件 95876；未匹配不代表安全。')
    parser.add_argument('--catalog', default=str(DEFAULT_CATALOG))
    for field in ('product', 'lot', 'upc', 'label-date'):
        parser.add_argument('--' + field, default='')
    args = parser.parse_args(argv)
    try:
        result = match_recall(load_catalog(args.catalog), {
            key: getattr(args, key) for key in ('product', 'lot', 'upc', 'label_date')})
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print(f'input error: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

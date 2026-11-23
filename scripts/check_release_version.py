"""Before a release publishes anything: the tag (vX.Y.Z), pyproject.toml, server.json (its version and its PyPI
package's) and the package's __version__ must be one version. Prints each and exits 1 when any differs.

Run: python scripts/check_release_version.py v0.2.1   (the release workflow passes $GITHUB_REF_NAME)"""
import ast
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def package_version() -> str | None:
    tree = ast.parse((ROOT / 'src' / 'ontology_poc_generator' / '__init__.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(getattr(t, 'id', None) == '__version__' for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def versions(tag: str) -> dict[str, str | None]:
    project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))['project']
    server = json.loads((ROOT / 'server.json').read_text(encoding='utf-8'))
    found = {'tag': tag[1:] if tag.startswith('v') else None,
             'pyproject.toml': project['version'],
             'server.json': server.get('version'),
             'ontology_poc_generator.__version__': package_version()}
    for p in server.get('packages', []):
        if p.get('registryType') == 'pypi':
            found[f"server.json package {p.get('identifier')}"] = p.get('version')
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print('usage: check_release_version.py vX.Y.Z', file=sys.stderr)
        return 2
    found = versions(argv[0])
    for where, version in found.items():
        print(f'{where}: {version}')
    if found['tag'] is None:
        print(f'the tag {argv[0]!r} does not start with v', file=sys.stderr)
        return 1
    if len(set(found.values())) != 1:
        print('these versions differ: nothing is published', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

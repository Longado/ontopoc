"""The `ontopoc` command a PyPI install gives: the MCP server, which is what `uvx ontopoc` and the MCP Registry run.
The OntoPoc service (page, API, examples) is not in the wheel; it runs from a clone or the Docker image, and the
MCP server talks to it at ONTOPOC_URL."""
from __future__ import annotations

import sys

from ontology_poc_generator import __version__

USAGE = f"""usage: ontopoc [mcp [--check]] | --version | --help

  ontopoc, ontopoc mcp   the OntoPoc MCP server on stdio, for an MCP client to start
  ontopoc mcp --check    one line if the OntoPoc service does not answer at ONTOPOC_URL, nothing if it does

Environment: ONTOPOC_URL (default http://127.0.0.1:8767), ONTOPOC_TOKEN (a personal token from the account page),
ONTOPOC_TOOLSET (read or all). The service itself is not in this package: run it from a clone of
https://github.com/Longado/ontopoc or its Docker image. ontopoc {__version__}"""


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else list(argv)
    if args in (['--version'], ['-V']):
        print(f'ontopoc {__version__}')
        return 0
    if args in (['--help'], ['-h'], ['help']):
        print(USAGE)
        return 0
    if not args or args[0] == 'mcp':
        from ontology_poc_generator import mcp_server
        mcp_server.main(args[1:])
        return 0
    print(f'ontopoc: unknown command {args[0]!r}\n\n{USAGE}', file=sys.stderr)
    raise SystemExit(2)


if __name__ == '__main__':
    raise SystemExit(main())

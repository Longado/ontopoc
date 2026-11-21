"""Starts an MCP server command, sends initialize, the initialized notification and tools/list over stdio, and checks
the answers: serverInfo names ontopoc and at least one tool is offered. Prints the server version and the tool count;
exits 1 otherwise. The release workflow runs it on the `ontopoc` command of the built wheel.

Run: python scripts/check_mcp_stdio.py -- ontopoc mcp"""
import json
import subprocess
import sys

MESSAGES = [
    {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
     'params': {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'release-check', 'version': '0'}}},
    {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
    {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
]


def main(argv: list[str]) -> int:
    command = argv[1:] if argv[:1] == ['--'] else argv
    if not command:
        print('usage: check_mcp_stdio.py -- COMMAND [ARGS...]', file=sys.stderr)
        return 2
    done = subprocess.run(command, input=''.join(json.dumps(m) + '\n' for m in MESSAGES),
                          capture_output=True, text=True, encoding='utf-8', timeout=60)
    replies = {r.get('id'): r for r in (json.loads(line) for line in done.stdout.splitlines() if line.strip())}
    try:
        info = replies[1]['result']['serverInfo']
        tools = replies[2]['result']['tools']
    except (KeyError, TypeError):
        print(f'no initialize and tools/list answers (exit {done.returncode})\nstdout: {done.stdout}\nstderr: {done.stderr}', file=sys.stderr)
        return 1
    if info.get('name') != 'ontopoc' or not tools:
        print(f'unexpected answers: serverInfo {info}, {len(tools)} tools', file=sys.stderr)
        return 1
    print(f"{info['name']} {info.get('version')}: protocol {replies[1]['result'].get('protocolVersion')}, {len(tools)} tools: "
          + ', '.join(t['name'] for t in tools))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))

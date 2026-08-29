from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ontology_poc_generator.errors import ScenarioValidationError
from ontology_poc_generator.generator import generate_proposal
from ontology_poc_generator.models import ScenarioParameters
from ontology_poc_generator.renderers import render_json, render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a decision-centered ontology POC proposal."
    )
    parser.add_argument("input", type=Path, help="Scenario JSON file")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="Write output to this file")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        params = ScenarioParameters.from_dict(raw)
        proposal = generate_proposal(params)
    except (OSError, json.JSONDecodeError, ScenarioValidationError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    content = (
        render_markdown(proposal) if args.format == "markdown" else render_json(proposal)
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

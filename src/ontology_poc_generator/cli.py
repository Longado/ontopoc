from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from ontology_poc_generator.errors import (
    KnowledgeValidationError,
    ScenarioValidationError,
)
from ontology_poc_generator.generator import generate_proposal
from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.models import ScenarioParameters
from ontology_poc_generator.renderers import render_json, render_markdown


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a decision-centered ontology POC proposal."
    )
    parser.add_argument("input", type=Path, help="Scenario JSON file")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="Write output to this file")
    parser.add_argument(
        "--knowledge-unit",
        dest="knowledge_units",
        action="append",
        type=Path,
        default=[],
        metavar="PATH",
        help="Load a candidate knowledge unit (repeatable, opt-in)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ScenarioValidationError("scenario must be an object")
        params = ScenarioParameters.from_dict(raw)
        knowledge_units = tuple(
            load_knowledge_unit(path) for path in args.knowledge_units
        )
        proposal = generate_proposal(params, knowledge_units)
        content = (
            render_markdown(proposal)
            if args.format == "markdown"
            else render_json(proposal)
        )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KnowledgeValidationError,
        ScenarioValidationError,
    ) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

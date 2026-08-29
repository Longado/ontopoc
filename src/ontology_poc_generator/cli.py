from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.errors import (
    KnowledgeValidationError,
    OntologySpecValidationError,
    ScenarioValidationError,
    SpecCompilationError,
)
from ontology_poc_generator.generator import generate_proposal
from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.models import ScenarioParameters
from ontology_poc_generator.ontology_spec import ClosureIssue, ontology_spec_to_dict
from ontology_poc_generator.renderers import render_json, render_markdown
from ontology_poc_generator.spec_compiler import compile_ontology_spec


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a decision-centered ontology POC proposal."
    )
    parser.add_argument("input", type=Path, help="Scenario JSON file")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--output", type=Path, help="Write output to this file")
    parser.add_argument(
        "--ontology-spec-output",
        type=Path,
        help="Write the compiled ontology spec envelope to this file",
    )
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


def _stage_output(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        temporary_path.write_text(content, encoding="utf-8")
    except (OSError, UnicodeError):
        temporary_path.unlink(missing_ok=True)
        raise
    return temporary_path


def _closure_issue_to_dict(issue: ClosureIssue) -> dict[str, object]:
    return {
        "issue_id": issue.issue_id,
        "code": issue.code,
        "owner_id": issue.owner_id,
        "field": issue.field,
        "referenced_id": issue.referenced_id,
    }


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
        ontology_spec_content = None
        if args.ontology_spec_output is not None:
            pack = compile_decision_pack(params, knowledge_units)
            compilation = compile_ontology_spec(pack)
            ontology_spec_content = json.dumps(
                {
                    "spec": ontology_spec_to_dict(compilation.spec),
                    "spec_content_hash": compilation.spec_content_hash,
                    "compilation_status": compilation.compilation_status.value,
                    "reference_closure": {
                        "is_closed": compilation.closure_report.is_closed,
                        "checked_reference_count": (
                            compilation.closure_report.checked_reference_count
                        ),
                        "issues": [
                            _closure_issue_to_dict(issue)
                            for issue in compilation.closure_report.issues
                        ],
                    },
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
    except (
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KnowledgeValidationError,
        OntologySpecValidationError,
        ScenarioValidationError,
        SpecCompilationError,
    ) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    if args.ontology_spec_output is not None:
        requested_outputs = []
        if args.output is not None:
            requested_outputs.append((args.output, content))
        requested_outputs.append((args.ontology_spec_output, ontology_spec_content))
        staged_outputs: list[tuple[Path, Path]] = []
        try:
            for path, staged_content in requested_outputs:
                staged_outputs.append((path, _stage_output(path, staged_content)))
            for path, temporary_path in staged_outputs:
                os.replace(temporary_path, path)
        except (OSError, UnicodeError) as exc:
            print(f"output error: {exc}", file=sys.stderr)
            return 3
        finally:
            for _, temporary_path in staged_outputs:
                try:
                    temporary_path.unlink()
                except FileNotFoundError:
                    pass
        if args.output is None:
            print(content, end="")
        return 0

    if args.output:
        try:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(content, encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            print(f"output error: {exc}", file=sys.stderr)
            return 3
    else:
        print(content, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

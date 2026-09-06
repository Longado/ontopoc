from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.decision_pack import render_decision_pack_json
from ontology_poc_generator.errors import (
    KnowledgeValidationError,
    OntologySpecValidationError,
    ScenarioValidationError,
    SpecCompilationError,
)
from ontology_poc_generator.generator import generate_proposal
from ontology_poc_generator.implementation_map import build_implementation_map
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
        "--decision-pack-output",
        type=Path,
        help="Write the canonical decision pack to this file",
    )
    parser.add_argument(
        "--implementation-map-output",
        type=Path,
        help="Write the read-only model-to-implementation map to this file",
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


def _backup_output(path: Path) -> Path | None:
    if not path.exists():
        return None
    descriptor, backup_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".bak",
    )
    os.close(descriptor)
    backup_path = Path(backup_name)
    try:
        shutil.copy2(path, backup_path)
    except (OSError, UnicodeError):
        backup_path.unlink(missing_ok=True)
        raise
    return backup_path


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
        decision_pack_content = None
        implementation_map_content = None
        if (
            args.ontology_spec_output is not None
            or args.decision_pack_output is not None
            or args.implementation_map_output is not None
        ):
            pack = compile_decision_pack(params, knowledge_units)
            if args.decision_pack_output is not None:
                decision_pack_content = render_decision_pack_json(pack)
        if (
            args.ontology_spec_output is not None
            or args.implementation_map_output is not None
        ):
            compilation = compile_ontology_spec(pack)
        if args.ontology_spec_output is not None:
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
        if args.implementation_map_output is not None:
            implementation_map_content = json.dumps(
                build_implementation_map(pack, compilation),
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

    if (
        args.ontology_spec_output is not None
        or args.decision_pack_output is not None
        or args.implementation_map_output is not None
    ):
        requested_outputs = []
        if args.output is not None:
            requested_outputs.append((args.output, content))
        if args.ontology_spec_output is not None:
            requested_outputs.append(
                (args.ontology_spec_output, ontology_spec_content)
            )
        if args.decision_pack_output is not None:
            requested_outputs.append(
                (args.decision_pack_output, decision_pack_content)
            )
        if args.implementation_map_output is not None:
            requested_outputs.append(
                (args.implementation_map_output, implementation_map_content)
            )
        try:
            resolved_outputs = [
                str(path.resolve()).casefold() for path, _ in requested_outputs
            ]
        except (OSError, RuntimeError) as exc:
            print(f"output error: {exc}", file=sys.stderr)
            return 3
        if len(set(resolved_outputs)) != len(resolved_outputs):
            print(
                "output error: output paths must resolve to different files",
                file=sys.stderr,
            )
            return 3
        staged_outputs: list[tuple[Path, Path]] = []
        backups: list[tuple[Path, Path | None]] = []
        installed_indexes: list[int] = []
        retained_backups: set[Path] = set()
        try:
            for path, staged_content in requested_outputs:
                staged_outputs.append((path, _stage_output(path, staged_content)))
            for path, _ in staged_outputs:
                backups.append((path, _backup_output(path)))
            for index, (path, temporary_path) in enumerate(staged_outputs):
                os.replace(temporary_path, path)
                installed_indexes.append(index)
        except (OSError, UnicodeError) as exc:
            rollback_errors = []
            for index in reversed(installed_indexes):
                path, backup_path = backups[index]
                try:
                    if backup_path is None:
                        path.unlink(missing_ok=True)
                    else:
                        os.replace(backup_path, path)
                except (OSError, UnicodeError) as rollback_exc:
                    rollback_errors.append(str(rollback_exc))
                    if backup_path is not None:
                        retained_backups.add(backup_path)
            print(f"output error: {exc}", file=sys.stderr)
            if rollback_errors:
                print(
                    f"rollback error: {'; '.join(rollback_errors)}",
                    file=sys.stderr,
                )
                for backup_path in sorted(retained_backups):
                    print(
                        f"recovery backup retained: {backup_path}",
                        file=sys.stderr,
                    )
            return 3
        finally:
            for _, temporary_path in staged_outputs:
                temporary_path.unlink(missing_ok=True)
            for _, backup_path in backups:
                if backup_path is not None and backup_path not in retained_backups:
                    backup_path.unlink(missing_ok=True)
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

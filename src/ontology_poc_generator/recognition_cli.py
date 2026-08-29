from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from ontology_poc_generator.errors import (
    KnowledgeValidationError,
    OntologySpecValidationError,
    ScenarioValidationError,
    SpecCompilationError,
)
from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.recognition import (
    RecognitionError,
    build_recognition_demo_envelope,
    recognize_scenario,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recognize one supported decision scenario and compile demo artifacts."
    )
    parser.add_argument("input", type=Path, help="UTF-8 business description")
    parser.add_argument("--api-base", help="OpenAI-compatible API base URL")
    parser.add_argument("--model", help="Configured model name")
    parser.add_argument(
        "--api-key-env",
        default="EIP_MODEL_API_KEY",
        help="Environment variable containing the model API key",
    )
    parser.add_argument("--output", type=Path, help="Write the demo envelope atomically")
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


def _write_atomic(path: Path, content: str) -> None:
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
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _validate_output_path(
    output: Path | None,
    input_path: Path,
    knowledge_units: list[Path],
) -> None:
    if output is None:
        return
    output_identity = os.fspath(output.resolve()).casefold()
    input_identities = {
        os.fspath(path.resolve()).casefold()
        for path in (input_path, *knowledge_units)
    }
    if output_identity in input_identities:
        raise ValueError("output path collides with an input path")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _validate_output_path(args.output, args.input, args.knowledge_units)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"output error: {exc}", file=sys.stderr)
        return 3
    try:
        api_base = args.api_base or os.environ.get("EIP_MODEL_API_BASE", "")
        model = args.model or os.environ.get("EIP_MODEL_NAME", "")
        api_key = os.environ.get(args.api_key_env, "")
        if not api_base:
            raise RecognitionError("api base is required")
        if not model:
            raise RecognitionError("model is required")
        if not api_key:
            raise RecognitionError(f"model API key is required in {args.api_key_env}")
        source_text = args.input.read_text(encoding="utf-8")
        gateway = OpenAICompatibleGateway(
            api_base=api_base,
            api_key=api_key,
            model=model,
        )
        result = recognize_scenario(source_text, gateway)
        knowledge_units = tuple(
            load_knowledge_unit(path) for path in args.knowledge_units
        )
        envelope = build_recognition_demo_envelope(result, knowledge_units)
        content = json.dumps(
            envelope,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    except (
        OSError,
        UnicodeError,
        KnowledgeValidationError,
        OntologySpecValidationError,
        RecognitionError,
        ScenarioValidationError,
        SpecCompilationError,
    ) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    if args.output is None:
        print(content)
        return 0
    try:
        _write_atomic(args.output, content)
    except (OSError, UnicodeError) as exc:
        print(f"output error: {exc}", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from ontology_poc_generator.agent_modeling import run_multi_agent_modeling
from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.recognition import RecognitionError
from ontology_poc_generator.recognition_cli import _validate_output_path, _write_atomic


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Propose and independently review an evidence-bound quality ontology model."
        )
    )
    parser.add_argument("input", type=Path, help="UTF-8 quality-event material")
    parser.add_argument("--api-base", help="OpenAI-compatible API base URL")
    parser.add_argument("--model", help="Configured model name")
    parser.add_argument(
        "--api-key-env",
        default="EIP_MODEL_API_KEY",
        help="Environment variable containing the model API key",
    )
    parser.add_argument("--output", type=Path, help="Write the reviewed model atomically")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _validate_output_path(args.output, args.input, [])
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
        decision_analyst_gateway = OpenAICompatibleGateway(
            api_base=api_base,
            api_key=api_key,
            model=model,
        )
        ontology_modeler_gateway = OpenAICompatibleGateway(
            api_base=api_base,
            api_key=api_key,
            model=model,
        )
        evidence_reviewer_gateway = OpenAICompatibleGateway(
            api_base=api_base,
            api_key=api_key,
            model=model,
        )
        result = run_multi_agent_modeling(
            source_text,
            decision_analyst_gateway,
            ontology_modeler_gateway,
            evidence_reviewer_gateway,
        )
        content = json.dumps(
            result,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
    except (OSError, UnicodeError, RecognitionError) as exc:
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

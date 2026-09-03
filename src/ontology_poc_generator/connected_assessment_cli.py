from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from ontology_poc_generator.connected_assessment import (
    run_connected_quality_assessment,
)
from ontology_poc_generator.enterprise_sources import (
    EnterpriseSourceError,
    load_enterprise_source_bundle,
    local_json_source_paths,
)
from ontology_poc_generator.model_gateway import OpenAICompatibleGateway
from ontology_poc_generator.recognition import RecognitionError
from ontology_poc_generator.recognition_cli import _validate_output_path, _write_atomic


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Assess a quality event from read-only ERP/MES/QMS/WMS/PLM evidence."
    )
    parser.add_argument("manifest", type=Path, help="Five-system source manifest")
    parser.add_argument("--api-base", help="OpenAI-compatible API base URL")
    parser.add_argument("--model", help="Configured model name")
    parser.add_argument(
        "--api-key-env",
        default="EIP_MODEL_API_KEY",
        help="Environment variable containing the model API key",
    )
    parser.add_argument("--output", type=Path, help="Write the assessment atomically")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _validate_output_path(args.output, args.manifest, [])
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
        bundle = load_enterprise_source_bundle(args.manifest)
    except (OSError, UnicodeError, EnterpriseSourceError, RecognitionError) as exc:
        print(f"input error: {exc}", file=sys.stderr)
        return 2

    try:
        _validate_output_path(
            args.output,
            args.manifest,
            list(local_json_source_paths(args.manifest)),
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"output error: {exc}", file=sys.stderr)
        return 3

    try:
        gateways = [
            OpenAICompatibleGateway(
                api_base=api_base,
                api_key=api_key,
                model=model,
            )
            for _ in range(4)
        ]
        result = run_connected_quality_assessment(bundle, *gateways)
        content = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2)
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

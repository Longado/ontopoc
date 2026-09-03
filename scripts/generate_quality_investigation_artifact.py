from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

from ontology_poc_generator.investigation_scope import (
    evaluate_control_scope,
    evaluate_investigation_scope,
)


ROOT = Path(__file__).parents[1]
SOURCE_SNAPSHOT = (
    ROOT
    / "tests/fixtures/quality/quality_investigation_source_snapshot_v1.json"
)
OUTPUT = ROOT / "landing-page/public/artifacts/quality-investigation.json"
FACTOR_PREDICATES = (
    "USES_BATCH",
    "BUILT_UNDER_VERSION",
    "EXECUTED_ON",
)


def build_artifact() -> dict[str, object]:
    source_snapshot = json.loads(SOURCE_SNAPSHOT.read_text(encoding="utf-8"))
    result = asdict(
        evaluate_investigation_scope(
            source_snapshot,
            quality_signal_id=source_snapshot["quality_signal_id"],
            factor_predicates=FACTOR_PREDICATES,
        )
    )
    for factor in result["factors"]:
        factor["status"] = factor["status"].value
    control_scope = asdict(
        evaluate_control_scope(
            source_snapshot,
            quality_signal_id=source_snapshot["quality_signal_id"],
        )
    )
    for item in control_scope["objects"]:
        item["status"] = item["status"].value
    return {
        "schema": result["schema"],
        "evidence_scope": "synthetic_demo",
        "source_snapshot_ref": str(SOURCE_SNAPSHOT.relative_to(ROOT)),
        "quality_signal_id": result["quality_signal_id"],
        "control_scope_objects": control_scope["objects"],
        "factors": result["factors"],
        "gaps": result["gaps"],
        "root_cause_confirmed": result["root_cause_confirmed"],
    }


def canonical_artifact_bytes(artifact: dict[str, object]) -> bytes:
    return (
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def main(
    argv: list[str] | None = None,
    *,
    output: Path = OUTPUT,
) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    content = canonical_artifact_bytes(build_artifact())

    if args.check:
        if not output.exists() or output.read_bytes() != content:
            print(f"stale artifact: {output}", file=sys.stderr)
            return 1
        return 0

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

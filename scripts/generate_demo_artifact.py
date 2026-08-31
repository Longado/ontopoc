"""Generate the committed, deterministic OntoPoc browser demo artifact."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.decision_pack import (
    DecisionPack,
    decision_pack_content_hash,
    decision_pack_to_dict,
)
from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.models import ScenarioParameters
from ontology_poc_generator.ontology_spec import (
    SpecCompilationResult,
    ontology_spec_to_dict,
)
from ontology_poc_generator.recognition import (
    ModelCompletion,
    build_recognition_demo_envelope,
    recognize_scenario,
)
from ontology_poc_generator.rule_runtime import (
    FactAvailability,
    SyntheticFact,
    SyntheticFactSet,
    evaluate_synthetic_rule,
    synthetic_fact_set_content_hash,
    synthetic_fact_set_to_dict,
)
from ontology_poc_generator.spec_compiler import compile_ontology_spec
from ontology_poc_generator.validation_receipt import (
    validation_receipt_content_hash,
    validation_receipt_to_dict,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "landing-page/public/artifacts/supply-chain-recognition.json"
BASELINE_POLICY = Path(
    "knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json"
)
CANDIDATE_POLICY = Path(
    "tests/fixtures/knowledge/order_priority_policy_synthetic_candidate_v2.json"
)
BOUNDARY_UNIT = Path(
    "knowledge/supply_chain/supplier_evidence_boundary_v1.json"
)
CASES_FIXTURE = Path(
    "tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json"
)
SOURCE_TEXT = (
    "synthetic_demo：供应链计划经理负责判断哪些订单进入优先干预队列；"
    "当订单预计交期、物料齐套或供应商承诺发生异常时，检查客户订单、物料与供应商关系。"
    "本材料为固定演示输入，不含客户事实，不触发发布、Action 或 ERP 写回。"
)


class DeterministicDemoGateway:
    """Recorded candidate gateway; it performs no network or live model call."""

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> ModelCompletion:
        del system_prompt, user_prompt
        candidate = {
            "schema": "scenario_intake_candidate.v1",
            "match_status": "matched",
            "profile_key": "order_priority_intervention",
            "decision_owner": "供应链计划经理",
            "trigger": "订单预计交期、物料齐套或供应商承诺发生异常时",
            "participant_keys": [
                "order_manager",
                "procurement_owner",
                "production_planner",
                "logistics_owner",
            ],
            "constraint_keys": [
                "erp_transaction_authority",
                "supplier_commitment_requires_evidence",
                "high_risk_requires_human_confirmation",
                "no_erp_writeback",
            ],
            "data_source_statuses": [
                {"source_key": "erp_order_material", "status": "to_confirm"},
                {
                    "source_key": "supplier_commitment_feedback",
                    "status": "to_confirm",
                },
                {"source_key": "logistics_node_status", "status": "unavailable"},
            ],
            "desired_action_keys": [
                "create_order_exception_review_task",
                "assign_procurement_or_planning_owner",
                "record_verdict_and_override_reason",
            ],
            "missing_required_fields": [],
        }
        return ModelCompletion(
            provider="recorded_demo_gateway",
            model="deterministic_demo_candidate_v1",
            content=json.dumps(candidate, ensure_ascii=False),
        )


def _compiled_variant(
    scenario: ScenarioParameters,
    policy_path: Path,
) -> tuple[DecisionPack, SpecCompilationResult]:
    units = tuple(
        load_knowledge_unit(ROOT / path)
        for path in (BOUNDARY_UNIT, policy_path)
    )
    pack = compile_decision_pack(scenario, units)
    return pack, compile_ontology_spec(pack)


def _variant_authority(
    policy_path: Path,
    pack: DecisionPack,
    compilation: SpecCompilationResult,
) -> dict[str, object]:
    return {
        "knowledge_unit": policy_path.as_posix(),
        "decision_pack": {
            "content_hash": decision_pack_content_hash(pack),
            "pack": decision_pack_to_dict(pack),
        },
        "ontology_spec": {
            "content_hash": compilation.spec_content_hash,
            "spec": ontology_spec_to_dict(compilation.spec),
        },
    }


def _synthetic_facts(
    compilation: SpecCompilationResult,
    case: dict[str, object],
) -> SyntheticFactSet:
    properties = {
        item.semantic_key: item.property_type_id
        for item in compilation.spec.property_types
    }
    subject_id = case["subject_id"]
    inputs = case["inputs"]
    assert isinstance(subject_id, str)
    assert isinstance(inputs, dict)
    facts = tuple(
        SyntheticFact(
            fact_ref=f"{subject_id}:{semantic_key}",
            property_type_id=properties[semantic_key],
            availability=FactAvailability(raw["availability"]),
            value=raw.get("value"),
            evidence_refs=(f"evidence:{subject_id}:{semantic_key}",),
        )
        for semantic_key, raw in inputs.items()
    )
    return SyntheticFactSet(
        schema="synthetic_fact_set.v1",
        evidence_scope="synthetic_demo",
        subject_id=subject_id,
        facts=facts,
    )


def _receipt_envelope(
    pack: DecisionPack,
    compilation: SpecCompilationResult,
    facts: SyntheticFactSet,
) -> dict[str, object]:
    rule_id = compilation.spec.rule_declarations[0].rule_id
    receipt = evaluate_synthetic_rule(pack, compilation, facts, rule_id)
    return {
        "content_hash": validation_receipt_content_hash(receipt),
        "receipt": validation_receipt_to_dict(receipt),
    }


def build_artifact() -> dict[str, object]:
    result = recognize_scenario(SOURCE_TEXT, DeterministicDemoGateway())
    baseline_pack, baseline_compilation = _compiled_variant(
        result.scenario,
        BASELINE_POLICY,
    )
    candidate_pack, candidate_compilation = _compiled_variant(
        result.scenario,
        CANDIDATE_POLICY,
    )
    baseline_units = tuple(
        load_knowledge_unit(ROOT / path)
        for path in (BOUNDARY_UNIT, BASELINE_POLICY)
    )
    artifact = build_recognition_demo_envelope(result, baseline_units)
    artifact["recording"] = {
        "mode": "recorded_deterministic_demo",
        "realtime_model_call": False,
        "source_text": SOURCE_TEXT,
    }
    fixture = json.loads((ROOT / CASES_FIXTURE).read_text(encoding="utf-8"))
    cases = []
    for case in fixture["cases"]:
        facts = _synthetic_facts(baseline_compilation, case)
        cases.append(
            {
                "subject_id": case["subject_id"],
                "facts": {
                    "content_hash": synthetic_fact_set_content_hash(facts),
                    "fact_set": synthetic_fact_set_to_dict(facts),
                },
                "baseline": _receipt_envelope(
                    baseline_pack,
                    baseline_compilation,
                    facts,
                ),
                "candidate": _receipt_envelope(
                    candidate_pack,
                    candidate_compilation,
                    facts,
                ),
            }
        )
    artifact["validation_run"] = {
        "schema": "validation_run.v1",
        "authority": {
            "evidence_scope": "synthetic_demo",
            "facts_fixture": CASES_FIXTURE.as_posix(),
            "baseline": {
                "knowledge_unit": BASELINE_POLICY.as_posix(),
                "decision_pack": {
                    "artifact_ref": "#/decision_pack",
                    "content_hash": decision_pack_content_hash(baseline_pack),
                },
                "ontology_spec": {
                    "artifact_ref": "#/ontology_spec",
                    "content_hash": baseline_compilation.spec_content_hash,
                },
            },
            "candidate": _variant_authority(
                CANDIDATE_POLICY,
                candidate_pack,
                candidate_compilation,
            ),
        },
        "runtime": {
            "mode": "recorded_deterministic",
            "evaluator": "ontology_poc_generator.rule_runtime.evaluate_synthetic_rule",
            "network_access": False,
            "external_writes": False,
        },
        "run_status": {
            "validation": "completed",
            "review": "not_started",
            "publication": "not_started",
            "action": "not_started",
            "external_write": False,
        },
        "cases": cases,
    }
    return artifact


def canonical_artifact_bytes(artifact: dict[str, object]) -> bytes:
    return (
        json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def write_artifact(output: Path, content: bytes) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main(argv: list[str] | None = None, *, output: Path = OUTPUT) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if the committed artifact differs; never write",
    )
    args = parser.parse_args(argv)
    content = canonical_artifact_bytes(build_artifact())
    if args.check:
        if not output.exists() or output.read_bytes() != content:
            print(f"artifact is missing or stale: {output}", file=sys.stderr)
            return 1
        return 0
    write_artifact(output, content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

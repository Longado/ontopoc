"""Generate the committed, deterministic OntoPoc browser demo artifact."""

from __future__ import annotations

import json
from pathlib import Path

from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.recognition import (
    ModelCompletion,
    build_recognition_demo_envelope,
    recognize_scenario,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "landing-page/public/artifacts/supply-chain-recognition.json"
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


def main() -> None:
    result = recognize_scenario(SOURCE_TEXT, DeterministicDemoGateway())
    knowledge_units = tuple(
        load_knowledge_unit(ROOT / path)
        for path in (
            "knowledge/supply_chain/supplier_evidence_boundary_v1.json",
            "knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json",
        )
    )
    artifact = build_recognition_demo_envelope(result, knowledge_units)
    artifact["recording"] = {
        "mode": "recorded_deterministic_demo",
        "realtime_model_call": False,
        "source_text": SOURCE_TEXT,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

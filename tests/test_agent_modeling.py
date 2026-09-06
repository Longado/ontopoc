import copy
import json
import unittest

from ontology_poc_generator.agent_modeling import run_multi_agent_modeling
from ontology_poc_generator.recognition import ModelCompletion, RecognitionError


SOURCE_TEXT = (
    "制造业质量经理负责在质量异常发生后决定哪些相关对象进入临时控制或复检队列。"
    "质量事件 QI-017 涉及物料批次 B-17。"
    "在制品 WIP-B17 使用物料批次 B-17。"
    "最终范围必须由质量经理人工确认，系统不得自动冻结库存。"
    "QMS 质量事件数据当前可用。MES 批次使用数据当前可用。"
    "验收时需要确认系统能否说明每个受影响对象的证据。"
)


def decision_contract(**required_overrides: object) -> dict[str, object]:
    required_fields: dict[str, object] = {
        "industry": {"value": "制造业", "evidence_span": "制造业"},
        "scene_name": {
            "value": "质量异常临时控制",
            "evidence_span": "质量异常发生后",
        },
        "business_decision": {
            "value": "哪些相关对象进入临时控制或复检队列",
            "evidence_span": "哪些相关对象进入临时控制或复检队列",
        },
        "decision_owner": {"value": "质量经理", "evidence_span": "质量经理"},
        "trigger": {
            "value": "质量异常发生后",
            "evidence_span": "质量异常发生后",
        },
    }
    required_fields.update(required_overrides)
    return {
        "schema": "decision_contract_candidate.v1",
        "required_fields": required_fields,
        "participants": [{"value": "质量经理", "evidence_span": "质量经理"}],
        "constraints": [
            {
                "value": "最终范围必须由质量经理人工确认",
                "evidence_span": "最终范围必须由质量经理人工确认",
            },
            {
                "value": "系统不得自动冻结库存",
                "evidence_span": "系统不得自动冻结库存",
            },
        ],
        "data_sources": [
            {
                "name": "QMS 质量事件数据",
                "source_type": "database",
                "status": "available",
                "evidence_span": "QMS 质量事件数据当前可用",
            },
            {
                "name": "MES 批次使用数据",
                "source_type": "database",
                "status": "available",
                "evidence_span": "MES 批次使用数据当前可用",
            },
        ],
        "desired_actions": [
            {
                "value": "形成临时控制或复检候选队列",
                "evidence_span": "进入临时控制或复检队列",
            }
        ],
        "acceptance_questions": [
            {
                "value": "系统能否说明每个受影响对象的证据？",
                "evidence_span": "系统能否说明每个受影响对象的证据",
            }
        ],
    }


def ontology_proposal() -> dict[str, object]:
    return {
        "schema": "ontology_candidate_proposal.v2",
        "objects": [
            {
                "candidate_key": "o1",
                "object_type": "quality_event",
                "evidence_span": "质量事件 QI-017",
            },
            {
                "candidate_key": "o2",
                "object_type": "material_batch",
                "evidence_span": "物料批次 B-17",
            },
            {
                "candidate_key": "o3",
                "object_type": "work_in_process",
                "evidence_span": "在制品 WIP-B17",
            },
        ],
        "relations": [
            {
                "candidate_key": "r1",
                "source_key": "o1",
                "predicate": "INVOLVES",
                "target_key": "o2",
                "evidence_span": "质量事件 QI-017 涉及物料批次 B-17",
            },
            {
                "candidate_key": "r2",
                "source_key": "o3",
                "predicate": "USES_BATCH",
                "target_key": "o2",
                "evidence_span": "在制品 WIP-B17 使用物料批次 B-17",
            },
        ],
    }


class StaticGateway:
    def __init__(self, payload: dict[str, object], model: str) -> None:
        self.payload = payload
        self.model = model
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> ModelCompletion:
        self.calls.append((system_prompt, user_prompt))
        return ModelCompletion(
            provider="openai_compatible",
            model=self.model,
            content=json.dumps(self.payload, ensure_ascii=False),
        )


class ReviewingGateway:
    def __init__(self, verdict_builder=None) -> None:
        self.verdict_builder = verdict_builder or self._accept_all
        self.calls: list[tuple[str, str]] = []

    @staticmethod
    def _accept_all(payload: dict[str, object]) -> list[dict[str, str]]:
        return [
            {
                "candidate_id": item["candidate_id"],
                "verdict": "accept",
                "reason": "原文直接支持",
            }
            for item in payload["review_items"]
        ]

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> ModelCompletion:
        self.calls.append((system_prompt, user_prompt))
        payload = json.loads(user_prompt)
        response = {
            "schema": "modeling_evidence_review.v1",
            "verdicts": self.verdict_builder(payload),
        }
        return ModelCompletion(
            provider="openai_compatible",
            model="reviewer-model",
            content=json.dumps(response, ensure_ascii=False),
        )


def run_session(
    contract: dict[str, object] | None = None,
    ontology: dict[str, object] | None = None,
    reviewer: ReviewingGateway | None = None,
) -> dict[str, object]:
    return run_multi_agent_modeling(
        SOURCE_TEXT,
        StaticGateway(contract or decision_contract(), "decision-model"),
        StaticGateway(ontology or ontology_proposal(), "ontology-model"),
        reviewer or ReviewingGateway(),
    )


class MultiAgentModelingTest(unittest.TestCase):
    def test_three_agents_compile_reviewed_draft_into_closed_product_artifacts(self) -> None:
        result = run_session()

        self.assertEqual(result["schema"], "multi_agent_modeling.v2")
        self.assertEqual(result["modeling_status"], "ready_for_human_confirmation")
        self.assertEqual(result["blocking_gaps"], [])
        self.assertEqual(
            [agent["role"] for agent in result["agents"]],
            ["decision_analyst", "ontology_modeler", "evidence_reviewer"],
        )
        pack = result["decision_pack"]["pack"]
        self.assertEqual(pack["schema"], "decision_pack.v1")
        self.assertEqual(
            pack["scenario"]["business_decision"],
            "哪些相关对象进入临时控制或复检队列",
        )
        self.assertEqual(
            {
                item["object_label"]
                for item in pack["scenario"]["object_role_bindings"]
            },
            {"质量事件", "物料批次", "在制品"},
        )
        ontology = result["ontology_spec"]
        self.assertEqual(ontology["compilation_status"], "complete")
        self.assertTrue(ontology["reference_closure"]["is_closed"])
        self.assertEqual(len(ontology["spec"]["entity_types"]), 3)
        self.assertEqual(len(ontology["spec"]["relation_types"]), 2)
        self.assertEqual(
            ontology["spec"]["pack_content_hash"],
            result["decision_pack"]["content_hash"],
        )
        self.assertTrue(result["boundaries"]["human_confirmation_required"])
        self.assertFalse(result["boundaries"]["ontology_authority_updated"])

    def test_model_response_order_does_not_change_draft_or_compilation(self) -> None:
        reordered_contract = copy.deepcopy(decision_contract())
        for field in (
            "participants",
            "constraints",
            "data_sources",
            "desired_actions",
            "acceptance_questions",
        ):
            reordered_contract[field] = list(reversed(reordered_contract[field]))
        reordered_ontology = copy.deepcopy(ontology_proposal())
        reordered_ontology["objects"] = list(reversed(reordered_ontology["objects"]))
        reordered_ontology["relations"] = list(
            reversed(reordered_ontology["relations"])
        )

        first = run_session()
        second = run_session(reordered_contract, reordered_ontology)

        for field in (
            "decision_contract_candidate",
            "ontology_candidates",
            "reviewer_accepted_draft",
            "decision_pack",
            "ontology_spec",
        ):
            self.assertEqual(first[field], second[field])

    def test_hallucinated_evidence_is_rejected_before_review(self) -> None:
        contract = decision_contract()
        contract["required_fields"]["industry"]["evidence_span"] = "航空航天业"
        reviewer = ReviewingGateway()

        with self.assertRaisesRegex(RecognitionError, "evidence_span.*source text"):
            run_session(contract=contract, reviewer=reviewer)

        self.assertEqual(reviewer.calls, [])

    def test_reviewer_must_cover_every_candidate_exactly_once(self) -> None:
        def omit_last(payload: dict[str, object]) -> list[dict[str, str]]:
            return ReviewingGateway._accept_all(payload)[:-1]

        with self.assertRaisesRegex(RecognitionError, "missing review verdicts"):
            run_session(reviewer=ReviewingGateway(omit_last))

    def test_accepted_relation_requires_accepted_endpoint_objects(self) -> None:
        def reject_batch(payload: dict[str, object]) -> list[dict[str, str]]:
            verdicts = ReviewingGateway._accept_all(payload)
            batch_id = next(
                item["candidate_id"]
                for item in payload["review_items"]
                if item.get("object_type") == "material_batch"
            )
            for verdict in verdicts:
                if verdict["candidate_id"] == batch_id:
                    verdict["verdict"] = "reject"
                    verdict["reason"] = "证据不足"
            return verdicts

        with self.assertRaisesRegex(
            RecognitionError, "accepted relation requires accepted endpoints"
        ):
            run_session(reviewer=ReviewingGateway(reject_batch))

    def test_missing_required_evidence_returns_typed_blocked_draft(self) -> None:
        result = run_session(contract=decision_contract(decision_owner=None))

        self.assertEqual(result["modeling_status"], "blocked_missing_evidence")
        self.assertEqual(result["blocking_gaps"], ["decision_owner"])
        self.assertIsNone(result["decision_pack"])
        self.assertIsNone(result["ontology_spec"])
        self.assertTrue(result["boundaries"]["human_confirmation_required"])

    def test_rejected_required_field_blocks_compilation_without_erasing_review(self) -> None:
        def reject_owner(payload: dict[str, object]) -> list[dict[str, str]]:
            verdicts = ReviewingGateway._accept_all(payload)
            owner_id = next(
                item["candidate_id"]
                for item in payload["review_items"]
                if item.get("field") == "decision_owner"
            )
            for verdict in verdicts:
                if verdict["candidate_id"] == owner_id:
                    verdict["verdict"] = "reject"
                    verdict["reason"] = "负责人表述不够明确"
            return verdicts

        result = run_session(reviewer=ReviewingGateway(reject_owner))

        self.assertEqual(result["modeling_status"], "blocked_missing_evidence")
        self.assertEqual(result["blocking_gaps"], ["decision_owner"])
        owner_review = next(
            item for item in result["reviews"] if item["verdict"] == "reject"
        )
        self.assertEqual(owner_review["reason"], "负责人表述不够明确")


if __name__ == "__main__":
    unittest.main()

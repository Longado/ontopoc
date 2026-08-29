import json
import unittest

from ontology_poc_generator.recognition import (
    ModelCompletion,
    RecognitionError,
    build_recognition_demo_envelope,
    recognize_scenario,
)


def candidate(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
        "schema": "scenario_recognition_candidate.v1",
        "profile": "order_priority_intervention",
        "industry": "制造业供应链",
        "scene_name": "订单履约异常识别",
        "business_decision": "哪些订单进入优先干预队列",
        "decision_owner": "供应链计划经理",
        "trigger": "订单交期或物料齐套状态异常时",
        "participants": ["订单经理", "采购负责人"],
        "additional_objects": ["订单行", "采购承诺"],
        "constraints": ["ERP 仍是交易事实权威"],
        "data_sources": [
            {"name": "ERP 订单数据", "type": "database", "status": "to_confirm"}
        ],
        "desired_actions": ["创建人工核查任务"],
        "acceptance_questions": ["能否解释候选队列依据？"],
        "notes": "只读演示，不回写 ERP。",
    }
    value.update(overrides)
    return value


class FakeGateway:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> ModelCompletion:
        self.calls.append((system_prompt, user_prompt))
        return ModelCompletion(
            provider="openai_compatible",
            model="demo-model",
            content=json.dumps(self.payload, ensure_ascii=False),
        )


class RecognitionContractTest(unittest.TestCase):
    def test_recognized_profile_uses_fixed_semantic_identity_and_safe_boundary(self) -> None:
        gateway = FakeGateway(candidate())

        result = recognize_scenario("订单可能延期，请识别干预场景。", gateway)

        self.assertEqual(result.prompt_version, "order_priority_intervention.v1")
        self.assertEqual(len(result.source_text_sha256), 64)
        self.assertEqual(result.provider, "openai_compatible")
        self.assertEqual(result.model, "demo-model")
        self.assertEqual(result.scenario.decision_key, "order_priority_intervention")
        self.assertFalse(result.scenario.customer_data_available)
        self.assertEqual(
            [(item.role_key, item.semantic_key, item.object_label) for item in result.scenario.object_role_bindings],
            [
                ("customer_order", "order.primary", "客户订单"),
                ("material", "material.required", "物料"),
                ("supplier", "supplier.candidate", "供应商"),
            ],
        )
        self.assertEqual(len(result.scenario.declared_bridges), 1)
        self.assertEqual(result.scenario.declared_bridges[0].predicate, "REQUIRES")
        self.assertEqual(result.scenario.readiness_declarations[0].status.value, "to_confirm")
        self.assertIn("订单可能延期", gateway.calls[0][1])

    def test_candidate_must_match_exact_non_executable_contract(self) -> None:
        invalid = candidate(score=0.9)

        with self.assertRaisesRegex(RecognitionError, "unexpected fields: score"):
            recognize_scenario("订单异常", FakeGateway(invalid))

    def test_unsupported_profile_fails_loudly(self) -> None:
        with self.assertRaisesRegex(RecognitionError, "unsupported profile"):
            recognize_scenario(
                "请选择供应商",
                FakeGateway(candidate(profile="supplier_selection")),
            )

    def test_model_response_must_be_a_json_object(self) -> None:
        class InvalidGateway:
            def complete_json(self, *, system_prompt: str, user_prompt: str) -> ModelCompletion:
                return ModelCompletion("openai_compatible", "demo-model", "not-json")

        with self.assertRaisesRegex(RecognitionError, "valid JSON object"):
            recognize_scenario("订单异常", InvalidGateway())

    def test_demo_envelope_compiles_closed_candidate_without_actions_or_facts(self) -> None:
        result = recognize_scenario("订单异常", FakeGateway(candidate()))

        envelope = build_recognition_demo_envelope(result)

        self.assertEqual(envelope["schema"], "model_recognition_demo.v1")
        self.assertEqual(len(envelope["decision_pack"]["content_hash"]), 64)
        self.assertEqual(len(envelope["ontology_spec"]["content_hash"]), 64)
        self.assertEqual(envelope["ontology_spec"]["compilation_status"], "complete")
        self.assertTrue(envelope["ontology_spec"]["reference_closure"]["is_closed"])
        serialized = json.dumps(envelope, ensure_ascii=False)
        for forbidden in (
            '"facts"',
            '"score"',
            '"actions_executed"',
            '"external_write"',
            '"published"',
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()

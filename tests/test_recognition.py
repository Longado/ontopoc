import json
from pathlib import Path
import unittest

from ontology_poc_generator.recognition import (
    ModelCompletion,
    RecognitionError,
    build_recognition_demo_envelope,
    recognize_scenario,
)
from ontology_poc_generator.models import ScenarioParameters


EXAMPLE_PATH = Path(__file__).parents[1] / "examples" / "supply_chain_exception.json"


def candidate(**overrides: object) -> dict[str, object]:
    value: dict[str, object] = {
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
            {"source_key": "supplier_commitment_feedback", "status": "to_confirm"},
            {"source_key": "logistics_node_status", "status": "unavailable"},
        ],
        "desired_action_keys": [
            "create_order_exception_review_task",
            "assign_procurement_or_planning_owner",
            "record_verdict_and_override_reason",
        ],
        "missing_required_fields": [],
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
    def test_matched_candidate_reconstructs_frozen_profile(self) -> None:
        expected = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        gateway = FakeGateway(candidate())

        result = recognize_scenario("订单可能延期，请识别干预场景。", gateway)

        self.assertEqual(result.prompt_version, "order_priority_intervention.v1")
        self.assertEqual(len(result.source_text_sha256), 64)
        self.assertEqual(result.provider, "openai_compatible")
        self.assertEqual(result.model, "demo-model")
        self.assertEqual(result.scenario, ScenarioParameters.from_dict(expected))
        self.assertIn("订单可能延期", gateway.calls[0][1])
        system_prompt = gateway.calls[0][0]
        self.assertIn("scenario_intake_candidate.v1", system_prompt)
        self.assertNotIn("additional_objects", system_prompt)
        self.assertNotIn("acceptance_questions", result.candidate)

    def test_candidate_rejects_extra_ontology_or_execution_fields(self) -> None:
        for field in (
            "objects",
            "participants",
            "constraints",
            "data_sources",
            "desired_actions",
            "semantic_key",
            "readiness_declarations",
            "customer_data_available",
            "rule",
            "score",
            "facts",
            "action",
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                RecognitionError, f"unexpected fields: {field}"
            ):
                recognize_scenario("订单异常", FakeGateway(candidate(**{field: []})))

    def test_controlled_keys_reject_unknown_and_duplicate_values(self) -> None:
        cases = (
            ("participant_keys", ["unknown_participant"], "unknown participant_keys"),
            (
                "constraint_keys",
                ["erp_transaction_authority", "erp_transaction_authority"],
                "duplicate constraint_keys",
            ),
            ("desired_action_keys", ["publish_queue"], "unknown desired_action_keys"),
            (
                "missing_required_fields",
                ["business_decision"],
                "unknown missing_required_fields",
            ),
        )
        for field, value, message in cases:
            with self.subTest(field=field), self.assertRaisesRegex(
                RecognitionError, message
            ):
                recognize_scenario("订单异常", FakeGateway(candidate(**{field: value})))

    def test_data_source_statuses_are_strict_and_unique(self) -> None:
        cases = (
            (
                [{"source_key": "unknown_source", "status": "to_confirm"}],
                "unknown data source key",
            ),
            (
                [{"source_key": "erp_order_material", "status": "confirmed"}],
                "unsupported data source status",
            ),
            (
                [
                    {"source_key": "erp_order_material", "status": "available"},
                    {"source_key": "erp_order_material", "status": "to_confirm"},
                ],
                "duplicate data source key",
            ),
            (
                [
                    {
                        "source_key": "erp_order_material",
                        "status": "to_confirm",
                        "name": "模型自定义 ERP",
                    }
                ],
                "must contain only source_key and status",
            ),
        )
        for statuses, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                RecognitionError, message
            ):
                recognize_scenario(
                    "订单异常",
                    FakeGateway(candidate(data_source_statuses=statuses)),
                )

    def test_array_reordering_produces_stable_candidate_and_scenario(self) -> None:
        original = candidate()
        reordered = candidate(
            participant_keys=list(reversed(original["participant_keys"])),
            constraint_keys=list(reversed(original["constraint_keys"])),
            data_source_statuses=list(reversed(original["data_source_statuses"])),
            desired_action_keys=list(reversed(original["desired_action_keys"])),
        )

        first = recognize_scenario("订单异常", FakeGateway(original))
        second = recognize_scenario("订单异常", FakeGateway(reordered))

        self.assertEqual(first.candidate_json, second.candidate_json)
        self.assertEqual(first.scenario, second.scenario)
        self.assertEqual(
            build_recognition_demo_envelope(first),
            build_recognition_demo_envelope(second),
        )

    def test_unmentioned_data_sources_default_to_review(self) -> None:
        result = recognize_scenario(
            "订单异常",
            FakeGateway(
                candidate(
                    data_source_statuses=[
                        {"source_key": "logistics_node_status", "status": "unavailable"}
                    ]
                )
            ),
        )

        self.assertEqual(
            [source.status for source in result.scenario.data_sources],
            ["to_confirm", "to_confirm", "unavailable"],
        )

    def test_insufficient_information_fails_without_profile_fallback(self) -> None:
        with self.assertRaisesRegex(RecognitionError, "insufficient information"):
            recognize_scenario(
                "订单异常",
                FakeGateway(
                    candidate(
                        match_status="insufficient_information",
                        decision_owner=None,
                        missing_required_fields=["decision_owner"],
                    )
                ),
            )

    def test_unsupported_fails_without_closest_profile_fallback(self) -> None:
        with self.assertRaisesRegex(RecognitionError, "unsupported scenario"):
            recognize_scenario(
                "请选择供应商",
                FakeGateway(
                    candidate(
                        match_status="unsupported",
                        profile_key=None,
                        decision_owner=None,
                        trigger=None,
                        participant_keys=[],
                        constraint_keys=[],
                        data_source_statuses=[],
                        desired_action_keys=[],
                    )
                ),
            )

    def test_matched_requires_complete_owner_trigger_and_no_missing_fields(self) -> None:
        cases = (
            ({"decision_owner": None}, "decision_owner is required"),
            ({"trigger": None}, "trigger is required"),
            (
                {"missing_required_fields": ["trigger"]},
                "matched candidate cannot have missing required fields",
            ),
            ({"profile_key": None}, "matched profile_key"),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides), self.assertRaisesRegex(
                RecognitionError, message
            ):
                recognize_scenario("订单异常", FakeGateway(candidate(**overrides)))

    def test_owner_and_trigger_are_bounded_extracted_text(self) -> None:
        cases = (
            ({"decision_owner": "责" * 81}, "decision_owner exceeds 80 characters"),
            ({"trigger": "异" * 301}, "trigger exceeds 300 characters"),
        )
        for overrides, message in cases:
            with self.subTest(overrides=overrides), self.assertRaisesRegex(
                RecognitionError, message
            ):
                recognize_scenario("订单异常", FakeGateway(candidate(**overrides)))

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

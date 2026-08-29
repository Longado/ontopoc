import hashlib
import json
from pathlib import Path
import re
import subprocess
import unittest

from ontology_poc_generator.errors import KnowledgeValidationError
from ontology_poc_generator.knowledge import (
    KnowledgeUnit,
    SourceKind,
    load_knowledge_unit,
)


VALID_HASH = "a" * 64
ROOT = Path(__file__).parents[1]
BASELINE_UNIT_PATH = (
    ROOT / "knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json"
)
CANDIDATE_UNIT_PATH = (
    ROOT / "tests/fixtures/knowledge/order_priority_policy_synthetic_candidate_v2.json"
)
CASES_PATH = (
    ROOT / "tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json"
)
SOURCE_NOTE_PATH = (
    ROOT
    / "knowledge/supply_chain/sources/order_priority_policy_synthetic_s1_v1.md"
)


def accepted_policy_unit_dict() -> dict:
    return {
        "unit_id": "supply_chain.order_priority.synthetic_policy_s1",
        "unit_version": "1.0.0",
        "decision_key": "order_priority_intervention",
        "applicability": {
            "required_role_keys": ["customer_order"],
            "required_bridges": [],
            "readiness_requirement_keys": [],
            "decision_mismatch_reason_code": "decision_key_mismatch",
            "missing_required_role_reason_code": "required_role_missing",
            "missing_required_bridge_reason_code": "required_bridge_missing",
        },
        "sources": [
            {
                "source_ref_id": "synthetic_order_priority_policy_cases_v1",
                "source_kind": "synthetic_example",
                "title": "Synthetic order-priority policy cases v1",
                "locator": "tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json",
                "revision": "fixture-blob",
                "snapshot_sha256": VALID_HASH,
                "caveat": (
                    "Synthetic test policy only; not a customer fact, industry "
                    "standard, or production threshold; defines no Action or score."
                ),
            }
        ],
        "suggestion_templates": [
            {
                "suggestion_id": "rule.order_priority.synthetic_s1",
                "contribution_type": "decision_rule",
                "payload_schema": "decision_rule.v1",
                "semantic_key": "order_priority_intervention_queue_rule",
                "payload": {
                    "rule_kind": "categorical_all_of_v1",
                    "subject_role_key": "customer_order",
                    "condition_1_semantic_key": "supplier_commitment_state",
                    "condition_1_allowed_values": "missed",
                    "condition_2_semantic_key": "qualified_alternative_state",
                    "condition_2_allowed_values": "none",
                    "output_conclusion_key": (
                        "priority_intervention_queue_membership"
                    ),
                    "positive_conclusion_value": "in_queue",
                    "negative_conclusion_value": "not_in_queue",
                    "description": "Synthetic categorical queue-entry policy.",
                    "evidence_scope": "synthetic_demo",
                },
                "input_binding_ids": ["customer_order"],
                "source_ref_ids": ["synthetic_order_priority_policy_cases_v1"],
                "governance_status": "candidate",
            }
        ],
    }


class SyntheticDecisionPolicyProfileTest(unittest.TestCase):
    def load(self, data: dict) -> KnowledgeUnit:
        return KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_accepts_only_the_frozen_decision_rule_fields(self):
        unit = self.load(accepted_policy_unit_dict())

        suggestion = unit.suggestion_templates[0]
        self.assertEqual(suggestion.contribution_type, "decision_rule")
        self.assertEqual(suggestion.payload_schema, "decision_rule.v1")
        self.assertEqual(
            dict(suggestion.payload)["rule_kind"], "categorical_all_of_v1"
        )

    def test_decision_rule_profile_requires_synthetic_demo_scope(self):
        data = accepted_policy_unit_dict()
        data["suggestion_templates"][0]["payload"]["evidence_scope"] = "customer"

        with self.assertRaisesRegex(
            KnowledgeValidationError,
            "decision_rule.v1 evidence_scope must be synthetic_demo",
        ):
            self.load(data)

    def test_rejects_unsupported_rule_kind(self):
        data = accepted_policy_unit_dict()
        data["suggestion_templates"][0]["payload"]["rule_kind"] = (
            "rolling_probability_v1"
        )

        with self.assertRaisesRegex(
            KnowledgeValidationError,
            "decision_rule.v1 rule_kind must be categorical_all_of_v1",
        ):
            self.load(data)

    def test_rejects_forbidden_executable_fields(self):
        for field in ("threshold", "expression", "score", "weight", "action"):
            data = accepted_policy_unit_dict()
            data["suggestion_templates"][0]["payload"][field] = "forbidden"
            with self.subTest(field=field), self.assertRaisesRegex(
                KnowledgeValidationError, f"payload key {field} is forbidden"
            ):
                self.load(data)

    def test_rejects_missing_or_extra_profile_fields(self):
        data = accepted_policy_unit_dict()
        data["suggestion_templates"][0]["payload"].pop("negative_conclusion_value")
        with self.assertRaisesRegex(
            KnowledgeValidationError,
            "payload keys must exactly match payload_schema",
        ):
            self.load(data)

    def test_rejects_empty_or_non_token_controlled_keys(self):
        fields = (
            "subject_role_key",
            "condition_1_semantic_key",
            "condition_2_semantic_key",
            "output_conclusion_key",
            "positive_conclusion_value",
            "negative_conclusion_value",
        )
        for field in fields:
            for value in (" ", "not a token", "UPPER_CASE", "123state"):
                data = accepted_policy_unit_dict()
                data["suggestion_templates"][0]["payload"][field] = value
                with self.subTest(field=field, value=value):
                    if not value.strip():
                        with self.assertRaises(KnowledgeValidationError):
                            self.load(data)
                    else:
                        with self.assertRaisesRegex(
                            KnowledgeValidationError,
                            f"decision_rule.v1 {field}",
                        ):
                            self.load(data)

    def test_rejects_valid_tokens_outside_the_frozen_s1_contract(self):
        replacements = {
            "subject_role_key": "sales_order",
            "condition_1_semantic_key": "delivery_state",
            "condition_2_semantic_key": "substitute_state",
            "output_conclusion_key": "review_queue_membership",
            "positive_conclusion_value": "review",
            "negative_conclusion_value": "skip",
        }
        for field, value in replacements.items():
            data = accepted_policy_unit_dict()
            data["suggestion_templates"][0]["payload"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                KnowledgeValidationError,
                f"decision_rule.v1 {field}",
            ):
                self.load(data)

    def test_rejects_non_token_identity_and_outer_whitespace(self):
        data = accepted_policy_unit_dict()
        data["suggestion_templates"][0]["semantic_key"] = "not a token"
        with self.assertRaisesRegex(
            KnowledgeValidationError,
            "decision_rule.v1 semantic_key",
        ):
            self.load(data)

        data = accepted_policy_unit_dict()
        data["suggestion_templates"][0]["payload"][
            "condition_1_allowed_values"
        ] = " at_risk,missed"
        with self.assertRaisesRegex(
            KnowledgeValidationError,
            "must not contain outer whitespace",
        ):
            self.load(data)

    def test_subject_role_must_be_bound_by_the_policy_template(self):
        data = accepted_policy_unit_dict()
        data["applicability"]["required_role_keys"].append("supplier")
        data["suggestion_templates"][0]["input_binding_ids"] = ["supplier"]

        with self.assertRaisesRegex(
            KnowledgeValidationError,
            "subject_role_key must be covered by input_binding_ids",
        ):
            self.load(data)

    def test_rejects_empty_non_token_duplicate_or_unsorted_allowed_values(self):
        invalid_values = (
            "",
            "at risk",
            "At_risk",
            "1",
            "missed,missed",
            "missed,at_risk",
            "at_risk, missed",
            "at_risk,",
        )
        for field in (
            "condition_1_allowed_values",
            "condition_2_allowed_values",
        ):
            for value in invalid_values:
                data = accepted_policy_unit_dict()
                data["suggestion_templates"][0]["payload"][field] = value
                with self.subTest(field=field, value=value):
                    if not value:
                        with self.assertRaises(KnowledgeValidationError):
                            self.load(data)
                    else:
                        with self.assertRaisesRegex(
                            KnowledgeValidationError,
                            f"decision_rule.v1 {field}",
                        ):
                            self.load(data)

    def test_policy_sources_must_all_be_synthetic_examples(self):
        for source_kind in (
            "provided_input",
            "authoritative_reference",
            "implemented_artifact",
            "observed_case",
            "practitioner_note",
        ):
            data = accepted_policy_unit_dict()
            data["sources"][0]["source_kind"] = source_kind
            with self.subTest(source_kind=source_kind), self.assertRaisesRegex(
                KnowledgeValidationError,
                "decision_rule.v1 sources must be synthetic_example",
            ):
                self.load(data)


class SyntheticDecisionPolicyFixtureTest(unittest.TestCase):
    def test_baseline_and_candidate_units_freeze_the_one_field_change(self):
        baseline = load_knowledge_unit(BASELINE_UNIT_PATH)
        candidate = load_knowledge_unit(CANDIDATE_UNIT_PATH)
        baseline_rule = baseline.suggestion_templates[0]
        candidate_rule = candidate.suggestion_templates[0]

        self.assertEqual(baseline_rule.semantic_key, candidate_rule.semantic_key)
        self.assertEqual(baseline_rule.payload_schema, "decision_rule.v1")
        self.assertEqual(candidate_rule.payload_schema, "decision_rule.v1")
        baseline_payload = dict(baseline_rule.payload)
        candidate_payload = dict(candidate_rule.payload)
        self.assertEqual(
            baseline_payload["condition_1_allowed_values"], "missed"
        )
        self.assertEqual(
            candidate_payload["condition_1_allowed_values"], "at_risk,missed"
        )
        baseline_payload["condition_1_allowed_values"] = "at_risk,missed"
        self.assertEqual(baseline_payload, candidate_payload)

    def test_policy_source_metadata_matches_the_case_fixture(self):
        cases_bytes = CASES_PATH.read_bytes()
        expected_sha256 = hashlib.sha256(cases_bytes).hexdigest()
        expected_blob = subprocess.run(
            ["git", "hash-object", str(CASES_PATH)],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

        for unit_path in (BASELINE_UNIT_PATH, CANDIDATE_UNIT_PATH):
            unit = load_knowledge_unit(unit_path)
            self.assertTrue(
                all(
                    source.source_kind is SourceKind.SYNTHETIC_EXAMPLE
                    for source in unit.source_refs
                )
            )
            self.assertEqual(unit.source_refs[0].snapshot_sha256, expected_sha256)
            self.assertEqual(unit.source_refs[0].revision, expected_blob)

        note = SOURCE_NOTE_PATH.read_text(encoding="utf-8")
        self.assertIn(expected_sha256, note)
        self.assertIn(expected_blob, note)
        for statement in (
            "synthetic test policy",
            "not a customer fact",
            "not an industry standard",
            "not a production threshold",
            "no Action or score",
        ):
            self.assertIn(statement, note)

    def test_case_fixture_freezes_four_addressable_loop3_expectations(self):
        fixture = json.loads(CASES_PATH.read_text(encoding="utf-8"))

        self.assertEqual(fixture["evidence_scope"], "synthetic_demo")
        self.assertEqual(
            [case["subject_id"] for case in fixture["cases"]],
            [
                "order.synthetic.001",
                "order.synthetic.002",
                "order.synthetic.003",
                "order.synthetic.004",
            ],
        )
        expected = {
            "order.synthetic.001": (
                ("pass", "in_queue"),
                ("pass", "in_queue"),
            ),
            "order.synthetic.002": (
                ("fail", "not_in_queue"),
                ("pass", "in_queue"),
            ),
            "order.synthetic.003": (
                ("fail", "not_in_queue"),
                ("fail", "not_in_queue"),
            ),
            "order.synthetic.004": (
                ("not_evaluable", "information_insufficient"),
                ("not_evaluable", "information_insufficient"),
            ),
        }
        for case in fixture["cases"]:
            with self.subTest(subject_id=case["subject_id"]):
                self.assertEqual(
                    (
                        case["expected"]["baseline"]["evaluation_status"],
                        case["expected"]["baseline"]["conclusion_value"],
                    ),
                    expected[case["subject_id"]][0],
                )
                self.assertEqual(
                    (
                        case["expected"]["candidate"]["evaluation_status"],
                        case["expected"]["candidate"]["conclusion_value"],
                    ),
                    expected[case["subject_id"]][1],
                )
        unavailable = fixture["cases"][3]["inputs"][
            "qualified_alternative_state"
        ]
        self.assertEqual(unavailable, {"availability": "unavailable"})
        self.assertNotIn("value", unavailable)

    def test_fixture_contains_no_action_score_or_numeric_policy_fields(self):
        text = CASES_PATH.read_text(encoding="utf-8")
        self.assertIsNone(re.search(r'"(?:action|score|weight|threshold)"\s*:', text))


if __name__ == "__main__":
    unittest.main()

import dataclasses
from dataclasses import FrozenInstanceError
import hashlib
import json
import unittest

import ontology_poc_generator.validation_receipt as receipt_module
from ontology_poc_generator.validation_receipt import (
    DecisionResult,
    EvaluationStatus,
    ValidationReceipt,
    ValidationReceiptValidationError,
    canonical_validation_receipt_json,
    validation_receipt_content_hash,
    validation_receipt_to_dict,
)


PACK_HASH = "a" * 64
SPEC_HASH = "b" * 64
FACTS_HASH = "c" * 64


def receipt_fixture(**overrides: object) -> ValidationReceipt:
    values = {
        "schema": "validation_receipt.v1",
        "decision_pack_content_hash": PACK_HASH,
        "ontology_spec_content_hash": SPEC_HASH,
        "facts_content_hash": FACTS_HASH,
        "rule_id": "rule_priority_queue",
        "evaluation_status": EvaluationStatus.PASS,
        "decision_result": DecisionResult.IN_QUEUE,
        "fact_refs": ("fact_order_state", "fact_supplier_state"),
        "evidence_refs": ("evidence_policy", "evidence_source_snapshot"),
        "draft_created": False,
        "published": False,
        "actions_executed": False,
        "external_write": False,
    }
    values.update(overrides)
    return ValidationReceipt(**values)


class ValidationReceiptContractTest(unittest.TestCase):
    def test_validation_receipt_contract_exposes_canonical_api(self):
        self.assertEqual(
            {
                "DecisionResult",
                "EvaluationStatus",
                "ValidationReceipt",
                "ValidationReceiptValidationError",
                "canonical_validation_receipt_json",
                "validation_receipt_content_hash",
                "validation_receipt_to_dict",
            },
            {
                name
                for name in (
                    "DecisionResult",
                    "EvaluationStatus",
                    "ValidationReceipt",
                    "ValidationReceiptValidationError",
                    "canonical_validation_receipt_json",
                    "validation_receipt_content_hash",
                    "validation_receipt_to_dict",
                )
                if hasattr(receipt_module, name)
            },
        )

    def test_enums_expose_only_the_four_frozen_states(self):
        self.assertEqual(
            tuple(item.value for item in EvaluationStatus),
            (
                "pass",
                "fail",
                "not_evaluable",
                "unsupported",
            ),
        )
        self.assertEqual(
            tuple(item.value for item in DecisionResult),
            (
                "in_queue",
                "not_in_queue",
                "information_insufficient",
                "unsupported",
            ),
        )
        with self.assertRaises(ValueError):
            EvaluationStatus("pending")
        with self.assertRaises(ValueError):
            DecisionResult("unknown")

    def test_receipt_is_frozen_and_requires_enum_members(self):
        self.assertTrue(dataclasses.is_dataclass(ValidationReceipt))
        receipt = receipt_fixture()

        with self.assertRaises(FrozenInstanceError):
            receipt.rule_id = "changed"
        with self.assertRaisesRegex(
            ValidationReceiptValidationError, "evaluation_status"
        ):
            receipt_fixture(evaluation_status="pass")
        with self.assertRaisesRegex(
            ValidationReceiptValidationError, "decision_result"
        ):
            receipt_fixture(decision_result="in_queue")

    def test_schema_is_exactly_validation_receipt_v1(self):
        for schema in ("validation_receipt.v2", " validation_receipt.v1", ""):
            with self.subTest(schema=schema), self.assertRaisesRegex(
                ValidationReceiptValidationError, "schema"
            ):
                receipt_fixture(schema=schema)

    def test_all_three_content_hash_bindings_require_strict_lowercase_sha256(self):
        for field in (
            "decision_pack_content_hash",
            "ontology_spec_content_hash",
            "facts_content_hash",
        ):
            for value in ("a" * 63, "A" * 64, "g" * 64, f"{'a' * 64} ", 7):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(
                    ValidationReceiptValidationError, field
                ):
                    receipt_fixture(**{field: value})

    def test_rule_and_reference_bindings_are_nonempty_unique_tuples(self):
        with self.assertRaisesRegex(ValidationReceiptValidationError, "rule_id"):
            receipt_fixture(rule_id=" ")

        for field in ("fact_refs", "evidence_refs"):
            for value in ([], (), ("",), ("same", "same")):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(
                    ValidationReceiptValidationError, field
                ):
                    receipt_fixture(**{field: value})

    def test_only_the_four_legal_status_result_pairs_are_accepted(self):
        legal_pairs = {
            EvaluationStatus.PASS: DecisionResult.IN_QUEUE,
            EvaluationStatus.FAIL: DecisionResult.NOT_IN_QUEUE,
            EvaluationStatus.NOT_EVALUABLE: DecisionResult.INFORMATION_INSUFFICIENT,
            EvaluationStatus.UNSUPPORTED: DecisionResult.UNSUPPORTED,
        }

        for status, result in legal_pairs.items():
            with self.subTest(status=status):
                self.assertEqual(
                    receipt_fixture(
                        evaluation_status=status,
                        decision_result=result,
                    ).decision_result,
                    result,
                )

        for status, legal_result in legal_pairs.items():
            for result in DecisionResult:
                if result is legal_result:
                    continue
                with self.subTest(status=status, result=result), self.assertRaisesRegex(
                    ValidationReceiptValidationError, "decision_result"
                ):
                    receipt_fixture(
                        evaluation_status=status,
                        decision_result=result,
                    )

    def test_all_delivery_boundary_fields_are_required_to_be_literal_false(self):
        for field in (
            "draft_created",
            "published",
            "actions_executed",
            "external_write",
        ):
            for value in (True, 0, None):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(
                    ValidationReceiptValidationError, field
                ):
                    receipt_fixture(**{field: value})

    def test_reference_order_does_not_change_canonical_bytes_or_content_hash(self):
        first = receipt_fixture(
            fact_refs=("fact_b", "fact_a"),
            evidence_refs=("evidence_b", "evidence_a"),
        )
        second = receipt_fixture(
            fact_refs=("fact_a", "fact_b"),
            evidence_refs=("evidence_a", "evidence_b"),
        )

        self.assertEqual(first.fact_refs, ("fact_a", "fact_b"))
        self.assertEqual(first.evidence_refs, ("evidence_a", "evidence_b"))
        self.assertEqual(
            canonical_validation_receipt_json(first),
            canonical_validation_receipt_json(second),
        )
        self.assertEqual(
            validation_receipt_content_hash(first),
            validation_receipt_content_hash(second),
        )

    def test_canonical_projection_is_explicit_repeatable_and_content_hashed(self):
        receipt = receipt_fixture(
            fact_refs=("fact_b", "fact_a"),
            evidence_refs=("evidence_b", "evidence_a"),
        )
        expected = {
            "schema": "validation_receipt.v1",
            "decision_pack_content_hash": PACK_HASH,
            "ontology_spec_content_hash": SPEC_HASH,
            "facts_content_hash": FACTS_HASH,
            "rule_id": "rule_priority_queue",
            "evaluation_status": "pass",
            "decision_result": "in_queue",
            "fact_refs": ["fact_a", "fact_b"],
            "evidence_refs": ["evidence_a", "evidence_b"],
            "draft_created": False,
            "published": False,
            "actions_executed": False,
            "external_write": False,
        }

        canonical = canonical_validation_receipt_json(receipt)
        self.assertEqual(validation_receipt_to_dict(receipt), expected)
        self.assertEqual(json.loads(canonical), expected)
        self.assertEqual(canonical, canonical_validation_receipt_json(receipt))
        self.assertEqual(
            validation_receipt_content_hash(receipt),
            hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()

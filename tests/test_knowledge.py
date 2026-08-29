import unittest
from dataclasses import FrozenInstanceError

from ontology_poc_generator.errors import KnowledgeValidationError
from ontology_poc_generator.knowledge import (
    KnowledgeSuggestion,
    KnowledgeUnit,
    SourceKind,
    SourceRef,
)


VALID_HASH = "a" * 64


def valid_unit_dict() -> dict:
    return {
        "unit_id": "supply_chain.order_priority.supplier_evidence_boundary",
        "unit_version": "1.0.0",
        "decision_key": "order_priority_intervention",
        "sources": [
            {
                "source_ref_id": "eip-vocabulary",
                "source_kind": "implemented_artifact",
                "title": "EIP vocabulary snapshot",
                "locator": "nano-ontoprompt/vocabulary.yaml#L19-L32",
                "revision": "snapshot-1",
                "snapshot_sha256": VALID_HASH,
                "caveat": "Implementation evidence, not a customer fact.",
            }
        ],
        "suggestion_templates": [
            {
                "suggestion_id": "qualified-to-supply",
                "contribution_type": "relation_semantics",
                "semantic_key": "supplier.qualified_to_supply.material",
                "payload": {
                    "predicate": "QUALIFIED_TO_SUPPLY",
                    "description": "Qualification and purchase history are distinct.",
                },
                "input_binding_ids": ["supplier", "material"],
                "source_ref_ids": ["eip-vocabulary"],
                "governance_status": "candidate",
            }
        ],
    }


class KnowledgeContractTest(unittest.TestCase):
    def test_contracts_are_frozen(self):
        source = SourceRef(
            source_ref_id="source-1",
            source_kind=SourceKind.IMPLEMENTED_ARTIFACT,
            title="Source",
            locator="repo/path",
            revision="revision-1",
            snapshot_sha256=VALID_HASH,
            caveat="Not a customer fact.",
        )
        suggestion = KnowledgeSuggestion(
            suggestion_id="suggestion-1",
            unit_id="unit-1",
            unit_version="1.0.0",
            unit_content_hash=VALID_HASH,
            contribution_type="constraint",
            semantic_key="evidence.boundary",
            payload=(("description", "History is not qualification."),),
            input_binding_ids=("supplier",),
            source_ref_ids=("source-1",),
        )
        unit = KnowledgeUnit(
            unit_id="unit-1",
            unit_version="1.0.0",
            decision_key="order_priority_intervention",
            unit_content_hash=VALID_HASH,
            source_refs=(source,),
            suggestion_templates=(suggestion,),
        )

        for value in (source, suggestion, unit):
            with self.subTest(value=type(value).__name__), self.assertRaises(
                FrozenInstanceError
            ):
                value.unit_id = "changed"

    def test_rejects_unknown_source_kind(self):
        data = valid_unit_dict()
        data["sources"][0]["source_kind"] = "blog_post"

        with self.assertRaisesRegex(KnowledgeValidationError, "source_kind"):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_rejects_missing_version(self):
        data = valid_unit_dict()
        data["unit_version"] = " "

        with self.assertRaisesRegex(KnowledgeValidationError, "unit_version is required"):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_rejects_missing_caveat(self):
        data = valid_unit_dict()
        data["sources"][0]["caveat"] = ""

        with self.assertRaisesRegex(KnowledgeValidationError, "caveat is required"):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_rejects_invalid_sha256(self):
        data = valid_unit_dict()
        data["sources"][0]["snapshot_sha256"] = "not-a-hash"

        with self.assertRaisesRegex(KnowledgeValidationError, "snapshot_sha256"):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_rejects_duplicate_source_ids(self):
        data = valid_unit_dict()
        data["sources"].append(dict(data["sources"][0]))

        with self.assertRaisesRegex(KnowledgeValidationError, "duplicate source_ref_id"):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_rejects_template_referencing_unknown_source(self):
        data = valid_unit_dict()
        data["suggestion_templates"][0]["source_ref_ids"] = ["missing"]

        with self.assertRaisesRegex(KnowledgeValidationError, "unknown source_ref_id"):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_rejects_duplicate_suggestion_ids(self):
        data = valid_unit_dict()
        data["suggestion_templates"].append(
            dict(data["suggestion_templates"][0])
        )

        with self.assertRaisesRegex(KnowledgeValidationError, "duplicate suggestion_id"):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_rejects_non_candidate_template(self):
        data = valid_unit_dict()
        data["suggestion_templates"][0]["governance_status"] = "confirmed"

        with self.assertRaisesRegex(KnowledgeValidationError, "must be candidate"):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_rejects_executable_or_result_payload_keys(self):
        for forbidden_key in (
            "threshold",
            "expression",
            "result",
            "action",
            "writeback",
        ):
            with self.subTest(forbidden_key=forbidden_key):
                data = valid_unit_dict()
                data["suggestion_templates"][0]["payload"][forbidden_key] = "x"

                with self.assertRaisesRegex(
                    KnowledgeValidationError, f"payload key {forbidden_key} is forbidden"
                ):
                    KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_accepted_unit_does_not_share_raw_mutable_data(self):
        data = valid_unit_dict()

        unit = KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)
        data["sources"][0]["title"] = "Changed"
        data["suggestion_templates"][0]["payload"]["predicate"] = "CHANGED"
        data["suggestion_templates"][0]["source_ref_ids"].append("new-source")

        self.assertEqual(unit.source_refs[0].title, "EIP vocabulary snapshot")
        self.assertEqual(
            dict(unit.suggestion_templates[0].payload)["predicate"],
            "QUALIFIED_TO_SUPPLY",
        )
        self.assertEqual(
            unit.suggestion_templates[0].source_ref_ids, ("eip-vocabulary",)
        )


if __name__ == "__main__":
    unittest.main()

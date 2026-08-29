import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import FrozenInstanceError
from unittest import mock

from ontology_poc_generator.errors import KnowledgeValidationError
from ontology_poc_generator.knowledge import (
    ApplicabilitySpec,
    KnowledgeSuggestion,
    KnowledgeUnit,
    SourceKind,
    SourceRef,
    load_knowledge_unit,
)


VALID_HASH = "a" * 64
UNIT_PATH = (
    Path(__file__).parents[1]
    / "knowledge/supply_chain/supplier_evidence_boundary_v1.json"
)
SOURCE_NOTE_PATH = (
    Path(__file__).parents[1]
    / "knowledge/supply_chain/sources/supplier_evidence_boundary_v1.md"
)

EXPECTED_SOURCE_IDS = (
    "eip_quality_vocabulary_v11",
    "eip_supply_chain_risk_qualification_history_tests",
    "loop1_product_methodology_snapshot",
)
EXPECTED_SUGGESTION_IDS = (
    "relation.qualified_to_supply",
    "relation.has_supplied",
    "constraint.history_not_qualification",
    "data_requirement.material_qualification_snapshot",
    "data_requirement.order_material_identity_mapping",
    "acceptance.qualification_absence_is_insufficient",
    "readiness.queue_entry_policy_pending",
)
EXPECTED_CONTRIBUTION_TYPES = (
    "relation_semantics",
    "relation_semantics",
    "constraint",
    "data_requirement",
    "data_requirement",
    "acceptance_question",
    "readiness_gap",
)
EXPECTED_PAYLOAD_SCHEMAS = (
    "relation_semantics.v1",
    "relation_semantics.v1",
    "constraint.narrative.v1",
    "data_requirement.narrative.v1",
    "data_requirement.narrative.v1",
    "acceptance_question.v1",
    "readiness_gap.v1",
)
EXPECTED_SOURCE_SNAPSHOTS = (
    "1e8b7bf0a128f716d55ab438a0830959dadd15cebcc91e576eee67e2ffd71425",
    "a937a6b085733766b09ff5f40468ef9e9b1182c946d1cff9a201947111d27ed8",
    "639616ae2ede7eece52d765992ed41b41b2fae1b36fbc0af1968123d16c95ba3",
)
EXPECTED_TEMPLATE_SOURCES = (
    ("eip_quality_vocabulary_v11",),
    ("eip_quality_vocabulary_v11",),
    (
        "eip_quality_vocabulary_v11",
        "eip_supply_chain_risk_qualification_history_tests",
    ),
    (
        "eip_quality_vocabulary_v11",
        "loop1_product_methodology_snapshot",
    ),
    ("loop1_product_methodology_snapshot",),
    ("eip_supply_chain_risk_qualification_history_tests",),
    ("loop1_product_methodology_snapshot",),
)


def valid_unit_dict() -> dict:
    return {
        "unit_id": "supply_chain.order_priority.supplier_evidence_boundary",
        "unit_version": "1.0.0",
        "decision_key": "order_priority_intervention",
        "applicability": {
            "required_role_keys": ["supplier", "material"],
            "required_bridges": [],
            "readiness_requirement_keys": [],
            "decision_mismatch_reason_code": "decision_key_mismatch",
            "missing_required_role_reason_code": "required_role_missing",
            "missing_required_bridge_reason_code": "required_bridge_missing",
        },
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
                "payload_schema": "relation_semantics.v1",
                "semantic_key": "supplier.qualified_to_supply.material",
                "payload": {
                    "source_role_key": "supplier",
                    "predicate": "QUALIFIED_TO_SUPPLY",
                    "target_role_key": "material",
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
            payload_schema="constraint.narrative.v1",
        )
        unit = KnowledgeUnit(
            unit_id="unit-1",
            unit_version="1.0.0",
            decision_key="order_priority_intervention",
            unit_content_hash=VALID_HASH,
            source_refs=(source,),
            suggestion_templates=(suggestion,),
            applicability=ApplicabilitySpec(
                required_role_keys=("supplier",),
                decision_mismatch_reason_code="decision_key_mismatch",
                missing_required_role_reason_code="required_role_missing",
                missing_required_bridge_reason_code="required_bridge_missing",
            ),
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

    def test_rejects_duplicate_runtime_suggestion_identity_seed(self):
        data = valid_unit_dict()
        duplicate = dict(data["suggestion_templates"][0])
        duplicate["suggestion_id"] = "different-declaration-id"
        data["suggestion_templates"].append(duplicate)

        with self.assertRaisesRegex(
            KnowledgeValidationError, "duplicate suggestion identity seed"
        ):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_applicability_rejects_casefold_key_collisions(self):
        mutations = (
            lambda data: data["applicability"]["required_role_keys"].append(
                "Supplier"
            ),
            lambda data: data["applicability"].update(
                {
                    "required_bridges": [
                        {
                            "semantic_key": "order_material",
                            "source_role_key": "supplier",
                            "predicate": "LINKS",
                            "target_role_key": "material",
                        },
                        {
                            "semantic_key": "ORDER_MATERIAL",
                            "source_role_key": "supplier",
                            "predicate": "LINKS",
                            "target_role_key": "material",
                        },
                    ]
                }
            ),
            lambda data: data["applicability"].update(
                {
                    "readiness_requirement_keys": [
                        "queue_policy",
                        "QUEUE_POLICY",
                    ]
                }
            ),
        )

        for mutate in mutations:
            data = valid_unit_dict()
            mutate(data)
            with self.subTest(data=data), self.assertRaisesRegex(
                KnowledgeValidationError, "duplicate"
            ):
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

    def test_direct_suggestion_keeps_legacy_default_until_added_to_a_unit(self):
        suggestion = KnowledgeSuggestion(
            "legacy", "unit", "1", VALID_HASH, "constraint", "key",
            (("description", "Candidate."),), ("supplier",), ("source",),
        )

        self.assertEqual(suggestion.payload_schema, "")
        with self.assertRaisesRegex(
            KnowledgeValidationError, "template payload_schema is required"
        ):
            KnowledgeUnit(
                "unit", "1", "decision", VALID_HASH,
                (
                    SourceRef(
                        "source", SourceKind.PRACTITIONER_NOTE, "Source", "local",
                        "1", VALID_HASH, "Not a customer fact.",
                    ),
                ),
                (suggestion,),
                ApplicabilitySpec(
                    required_role_keys=("supplier",),
                    decision_mismatch_reason_code="decision_mismatch",
                    missing_required_role_reason_code="role_missing",
                    missing_required_bridge_reason_code="bridge_missing",
                ),
            )

    def test_rejects_unknown_or_mismatched_payload_schema(self):
        cases = (
            ("unknown.v1", "relation_semantics", "unknown payload_schema"),
            (
                "constraint.narrative.v1",
                "relation_semantics",
                "payload_schema does not match contribution_type",
            ),
        )
        for payload_schema, contribution_type, message in cases:
            data = valid_unit_dict()
            data["suggestion_templates"][0]["payload_schema"] = payload_schema
            data["suggestion_templates"][0]["contribution_type"] = contribution_type
            with self.subTest(payload_schema=payload_schema), self.assertRaisesRegex(
                KnowledgeValidationError, message
            ):
                KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_loader_rejects_missing_payload_schema(self):
        data = valid_unit_dict()
        data["suggestion_templates"][0].pop("payload_schema")

        with self.assertRaisesRegex(
            KnowledgeValidationError, "payload_schema is required"
        ):
            KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_rejects_missing_extra_or_empty_profile_payload_fields(self):
        mutations = (
            lambda payload: payload.pop("target_role_key"),
            lambda payload: payload.update({"extra": "not allowed"}),
            lambda payload: payload.update({"description": " "}),
        )
        for mutate in mutations:
            data = valid_unit_dict()
            mutate(data["suggestion_templates"][0]["payload"])
            with self.subTest(payload=data["suggestion_templates"][0]["payload"]), \
                    self.assertRaises(KnowledgeValidationError):
                KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

    def test_relation_profile_endpoints_must_be_declared_and_bound(self):
        cases = (
            ("source_role_key", "unknown", "unknown applicability role"),
            ("target_role_key", "unknown", "unknown applicability role"),
        )
        for field, value, message in cases:
            data = valid_unit_dict()
            data["suggestion_templates"][0]["payload"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                KnowledgeValidationError, message
            ):
                KnowledgeUnit.from_dict(data, unit_content_hash=VALID_HASH)

        data = valid_unit_dict()
        data["suggestion_templates"][0]["input_binding_ids"] = ["supplier"]
        with self.assertRaisesRegex(
            KnowledgeValidationError, "relation endpoints must be covered"
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


class KnowledgeLoaderTest(unittest.TestCase):
    def test_loads_fixed_supplier_evidence_unit_in_stable_order(self):
        unit = load_knowledge_unit(UNIT_PATH)

        self.assertEqual(
            unit.unit_id,
            "supply_chain.order_priority.supplier_evidence_boundary",
        )
        self.assertEqual(unit.unit_version, "1.0.0")
        self.assertEqual(unit.decision_key, "order_priority_intervention")
        self.assertEqual(
            tuple(source.source_ref_id for source in unit.source_refs),
            EXPECTED_SOURCE_IDS,
        )
        self.assertEqual(
            tuple(source.source_kind.value for source in unit.source_refs),
            ("implemented_artifact", "synthetic_example", "practitioner_note"),
        )
        self.assertEqual(
            tuple(source.snapshot_sha256 for source in unit.source_refs),
            EXPECTED_SOURCE_SNAPSHOTS,
        )
        self.assertEqual(
            tuple(item.suggestion_id for item in unit.suggestion_templates),
            EXPECTED_SUGGESTION_IDS,
        )
        self.assertEqual(
            tuple(item.contribution_type for item in unit.suggestion_templates),
            EXPECTED_CONTRIBUTION_TYPES,
        )
        self.assertEqual(
            tuple(item.payload_schema for item in unit.suggestion_templates),
            EXPECTED_PAYLOAD_SCHEMAS,
        )
        self.assertEqual(
            tuple(item.source_ref_ids for item in unit.suggestion_templates),
            EXPECTED_TEMPLATE_SOURCES,
        )
        self.assertEqual(
            unit.applicability.required_role_keys,
            ("customer_order", "material", "supplier"),
        )
        self.assertEqual(
            tuple(bridge.semantic_key for bridge in unit.applicability.required_bridges),
            ("customer_order_requires_material",),
        )
        self.assertEqual(
            unit.applicability.readiness_requirement_keys,
            ("queue_entry_evidence_policy",),
        )
        self.assertEqual(
            unit.applicability.decision_mismatch_reason_code,
            "decision_key_mismatch",
        )
        self.assertEqual(
            unit.applicability.missing_required_role_reason_code,
            "required_role_missing",
        )
        self.assertEqual(
            unit.applicability.missing_required_bridge_reason_code,
            "order_material_bridge_missing",
        )

    def test_applicability_rejects_template_role_outside_declared_roles(self):
        raw = json.loads(UNIT_PATH.read_text(encoding="utf-8"))
        raw["suggestion_templates"][0]["input_binding_ids"].append("unknown_role")

        with self.assertRaisesRegex(
            KnowledgeValidationError, "unknown applicability role"
        ):
            KnowledgeUnit.from_dict(raw, unit_content_hash=VALID_HASH)

    def test_applicability_rejects_bridge_role_outside_declared_roles(self):
        raw = json.loads(UNIT_PATH.read_text(encoding="utf-8"))
        raw["applicability"]["required_bridges"][0]["target_role_key"] = "unknown_role"

        with self.assertRaisesRegex(
            KnowledgeValidationError, "bridge references unknown role"
        ):
            KnowledgeUnit.from_dict(raw, unit_content_hash=VALID_HASH)

    def test_readiness_gap_must_reference_a_declared_requirement(self):
        raw = json.loads(UNIT_PATH.read_text(encoding="utf-8"))
        raw["suggestion_templates"][-1]["payload"]["requirement_key"] = "unknown"

        with self.assertRaisesRegex(
            KnowledgeValidationError, "unknown readiness requirement"
        ):
            KnowledgeUnit.from_dict(raw, unit_content_hash=VALID_HASH)

    def test_readiness_gap_is_rejected_when_no_requirements_are_declared(self):
        raw = json.loads(UNIT_PATH.read_text(encoding="utf-8"))
        raw["applicability"]["readiness_requirement_keys"] = []

        with self.assertRaisesRegex(
            KnowledgeValidationError, "unknown readiness requirement"
        ):
            KnowledgeUnit.from_dict(raw, unit_content_hash=VALID_HASH)

    def test_applicability_rejects_duplicate_requirements(self):
        mutations = (
            (
                "required_role_keys",
                "customer_order",
                "duplicate required_role_key",
            ),
            (
                "readiness_requirement_keys",
                "queue_entry_evidence_policy",
                "duplicate readiness_requirement_key",
            ),
        )
        for field, duplicate, expected_error in mutations:
            with self.subTest(field=field):
                raw = json.loads(UNIT_PATH.read_text(encoding="utf-8"))
                raw["applicability"][field].append(duplicate)

                with self.assertRaisesRegex(
                    KnowledgeValidationError, expected_error
                ):
                    KnowledgeUnit.from_dict(raw, unit_content_hash=VALID_HASH)

    def test_applicability_rejects_duplicate_bridge_semantic_keys(self):
        raw = json.loads(UNIT_PATH.read_text(encoding="utf-8"))
        raw["applicability"]["required_bridges"].append(
            dict(raw["applicability"]["required_bridges"][0])
        )

        with self.assertRaisesRegex(
            KnowledgeValidationError, "duplicate required bridge semantic_key"
        ):
            KnowledgeUnit.from_dict(raw, unit_content_hash=VALID_HASH)

    def test_repeated_loads_have_same_canonical_content_hash(self):
        first = load_knowledge_unit(UNIT_PATH)
        second = load_knowledge_unit(UNIT_PATH)

        self.assertEqual(first.unit_content_hash, second.unit_content_hash)
        self.assertRegex(first.unit_content_hash, r"^[0-9a-f]{64}$")

    def test_legal_content_change_changes_unit_hash_not_source_snapshots(self):
        original = load_knowledge_unit(UNIT_PATH)
        raw = json.loads(UNIT_PATH.read_text(encoding="utf-8"))
        raw["suggestion_templates"][2]["payload"]["description"] += " Candidate only."

        with tempfile.TemporaryDirectory() as directory:
            changed_path = Path(directory) / "changed.json"
            changed_path.write_text(
                json.dumps(raw, ensure_ascii=False),
                encoding="utf-8",
            )
            changed = load_knowledge_unit(changed_path)

        self.assertNotEqual(original.unit_content_hash, changed.unit_content_hash)
        self.assertEqual(
            tuple(source.snapshot_sha256 for source in original.source_refs),
            tuple(source.snapshot_sha256 for source in changed.source_refs),
        )

    def test_loader_reads_only_the_supplied_package(self):
        accessed: list[Path] = []
        original_open = Path.open

        def guarded_open(path: Path, *args, **kwargs):
            resolved = Path(path).resolve()
            accessed.append(resolved)
            self.assertNotIn("nano-ontoprompt", str(resolved))
            return original_open(path, *args, **kwargs)

        with mock.patch.object(Path, "open", guarded_open):
            load_knowledge_unit(UNIT_PATH)

        self.assertEqual(accessed, [UNIT_PATH.resolve()])

    def test_source_note_records_locator_hash_caveat_and_supported_ids(self):
        note = SOURCE_NOTE_PATH.read_text(encoding="utf-8")

        for expected in (
            "nano-ontoprompt",
            "backend/app/eip_extensions/quality/vocabulary.yaml",
            "lines 19-32",
            "1e8b7bf0a128f716d55ab438a0830959dadd15cebcc91e576eee67e2ffd71425",
            "backend/tests/test_eip_supply_chain_risk.py",
            "qualification/history cases",
            "a937a6b085733766b09ff5f40468ef9e9b1182c946d1cff9a201947111d27ed8",
            "310c4d07bcc975fa955dea7a29f5dc7cc12172e4",
            "639616ae2ede7eece52d765992ed41b41b2fae1b36fbc0af1968123d16c95ba3",
            "product methodology assumption, not a customer or industry fact",
        ) + EXPECTED_SUGGESTION_IDS:
            with self.subTest(expected=expected):
                self.assertIn(expected, note)

    def test_templates_remain_candidate_and_do_not_claim_execution_or_results(self):
        unit = load_knowledge_unit(UNIT_PATH)
        forbidden_keys = {"threshold", "expression", "result", "action", "writeback"}
        forbidden_claims = (
            "final queue",
            "final order",
            "risk score",
            "order conclusion",
            "最终队列",
            "最终订单结论",
            "处置动作",
        )

        self.assertEqual(len(unit.suggestion_templates), 7)
        for template in unit.suggestion_templates:
            with self.subTest(suggestion_id=template.suggestion_id):
                payload = dict(template.payload)
                self.assertEqual(template.governance_status, "candidate")
                self.assertTrue(all(isinstance(value, str) for value in payload.values()))
                self.assertTrue(forbidden_keys.isdisjoint(key.casefold() for key in payload))
                rendered = json.dumps(payload, ensure_ascii=False).casefold()
                for claim in forbidden_claims:
                    self.assertNotIn(claim.casefold(), rendered)

        predicates = tuple(
            dict(template.payload).get("predicate")
            for template in unit.suggestion_templates
            if template.contribution_type == "relation_semantics"
        )
        self.assertEqual(predicates, ("QUALIFIED_TO_SUPPLY", "HAS_SUPPLIED"))
        self.assertNotIn("SUPPLIES", predicates)

        qualification_snapshot = next(
            template
            for template in unit.suggestion_templates
            if template.suggestion_id
            == "data_requirement.material_qualification_snapshot"
        )
        description = dict(qualification_snapshot.payload)["description"]
        for required_detail in (
            "qualification status",
            "validity",
            "scope",
            "snapshot completeness",
        ):
            with self.subTest(required_detail=required_detail):
                self.assertIn(required_detail, description)


if __name__ == "__main__":
    unittest.main()

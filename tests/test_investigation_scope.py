import importlib
import copy
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SNAPSHOT_PATH = (
    ROOT
    / "tests/fixtures/quality/quality_investigation_source_snapshot_v1.json"
)
ENTERPRISE_MANIFEST = ROOT / "tests/fixtures/enterprise_sources/manifest.json"
FACTOR_PREDICATES = (
    "USES_BATCH",
    "BUILT_UNDER_VERSION",
    "EXECUTED_ON",
)


def investigation_module():
    try:
        return importlib.import_module("ontology_poc_generator.investigation_scope")
    except ModuleNotFoundError:
        raise AssertionError("investigation_scope module is not implemented") from None


def source_snapshot():
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


class InvestigationScopeTest(unittest.TestCase):
    def test_source_relations_derive_all_four_control_scope_states(self):
        investigation = investigation_module()
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        snapshot = load_enterprise_source_bundle(ENTERPRISE_MANIFEST)[
            "source_snapshot"
        ]
        result = investigation.evaluate_control_scope(
            snapshot,
            quality_signal_id="quality-event-017",
        )

        self.assertEqual(result.schema, "control_scope.v1")
        self.assertEqual(
            tuple(
                (item.object_id, item.object_type, item.status.value)
                for item in result.objects
            ),
            (
                ("inventory-lot-017", "inventory", "confirmed_impact"),
                ("work-order-wip-204", "work_in_process", "confirmed_impact"),
                ("pending-shipment-031", "pending_shipment", "possible_impact"),
                ("in-transit-shipment-044", "in_transit", "excluded"),
                ("customer-unit-group-017", "customer_side", "not_evaluable"),
            ),
        )
        self.assertFalse(result.root_cause_confirmed)

    def test_control_scope_rejects_self_declared_production_evidence(self):
        investigation = investigation_module()
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        snapshot = load_enterprise_source_bundle(ENTERPRISE_MANIFEST)[
            "source_snapshot"
        ]
        snapshot["evidence_scope"] = "authorized_read_only"

        with self.assertRaisesRegex(
            investigation.InvestigationScopeError, "synthetic_demo"
        ):
            investigation.evaluate_control_scope(
                snapshot,
                quality_signal_id="quality-event-017",
            )

    def test_control_scope_keeps_exact_evidence_for_each_judgment(self):
        investigation = investigation_module()
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        snapshot = load_enterprise_source_bundle(ENTERPRISE_MANIFEST)[
            "source_snapshot"
        ]
        result = investigation.evaluate_control_scope(
            snapshot,
            quality_signal_id="quality-event-017",
        )
        by_id = {item.object_id: item for item in result.objects}

        self.assertEqual(
            by_id["inventory-lot-017"].evidence_refs,
            (
                "mes:material-use-abnormal-017",
                "qms:inspection-abnormal-017",
                "qms:quality-event-017",
                "wms:inventory-batch-017",
            ),
        )
        self.assertEqual(
            by_id["pending-shipment-031"].evidence_refs,
            (
                "mes:process-version-abnormal-017",
                "qms:inspection-abnormal-017",
                "qms:quality-event-017",
                "wms:pending-shipment-031",
            ),
        )
        self.assertEqual(
            by_id["in-transit-shipment-044"].evidence_refs,
            (
                "mes:material-use-normal-021",
                "qms:inspection-abnormal-017",
                "qms:inspection-normal-021",
                "qms:quality-event-017",
                "wms:in-transit-044",
            ),
        )
        self.assertEqual(
            by_id["customer-unit-group-017"].evidence_refs,
            (
                "plm:missing-project-product-map-017",
                "qms:inspection-abnormal-017",
                "qms:quality-event-017",
            ),
        )

    def test_identified_subject_must_have_one_explicit_abnormal_outcome(self):
        investigation = investigation_module()
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        snapshot = load_enterprise_source_bundle(ENTERPRISE_MANIFEST)[
            "source_snapshot"
        ]
        normal_only = copy.deepcopy(snapshot)
        outcome = next(
            record
            for record in normal_only["records"]
            if record["source_record_id"] == "inspection-abnormal-017"
        )
        outcome["object_id"] = "normal"
        with self.assertRaisesRegex(
            investigation.InvestigationScopeError, "explicit abnormal"
        ):
            investigation.evaluate_control_scope(
                normal_only, quality_signal_id="quality-event-017"
            )

        conflicting = copy.deepcopy(snapshot)
        conflicting["records"].append(
            {
                **outcome,
                "source_record_id": "inspection-conflict-017",
                "evidence_ref": "qms:inspection-conflict-017",
            }
        )
        with self.assertRaisesRegex(
            investigation.InvestigationScopeError, "conflicting inspection outcomes"
        ):
            investigation.evaluate_control_scope(
                conflicting, quality_signal_id="quality-event-017"
            )

    def test_object_is_excluded_only_when_all_known_batches_have_normal_controls(self):
        investigation = investigation_module()
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        snapshot = load_enterprise_source_bundle(ENTERPRISE_MANIFEST)[
            "source_snapshot"
        ]
        mixed = copy.deepcopy(snapshot)
        mixed["records"].append(
            {
                "source_system": "WMS",
                "source_record_id": "in-transit-unknown-batch-044",
                "observed_at": "2026-09-02T09:00:00+08:00",
                "subject_id": "in-transit-shipment-044",
                "predicate": "USES_BATCH",
                "object_id": "component-batch-unknown",
                "availability": "available",
                "evidence_ref": "wms:in-transit-unknown-batch-044",
            }
        )

        result = investigation.evaluate_control_scope(
            mixed, quality_signal_id="quality-event-017"
        )
        item = next(
            value
            for value in result.objects
            if value.object_id == "in-transit-shipment-044"
        )
        self.assertEqual(item.status.value, "not_evaluable")
        self.assertIn("wms:in-transit-unknown-batch-044", item.evidence_refs)

    def test_object_with_a_normal_batch_and_an_open_link_is_not_excluded(self):
        investigation = investigation_module()
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        snapshot = load_enterprise_source_bundle(ENTERPRISE_MANIFEST)[
            "source_snapshot"
        ]
        open_link = copy.deepcopy(snapshot)
        open_link["records"].append(
            {
                "source_system": "PLM",
                "source_record_id": "in-transit-project-map-044",
                "observed_at": "2026-09-02T09:00:00+08:00",
                "subject_id": "in-transit-shipment-044",
                "predicate": "MAPPED_TO_PROJECT",
                "object_id": None,
                "availability": "missing",
                "evidence_ref": "plm:missing-in-transit-project-map-044",
            }
        )

        result = investigation.evaluate_control_scope(
            open_link, quality_signal_id="quality-event-017"
        )
        item = next(
            value
            for value in result.objects
            if value.object_id == "in-transit-shipment-044"
        )
        self.assertEqual(item.status.value, "not_evaluable")
        self.assertIn("plm:missing-in-transit-project-map-044", item.evidence_refs)

    def test_each_control_object_must_have_one_unambiguous_type(self):
        investigation = investigation_module()
        from ontology_poc_generator.enterprise_sources import (
            load_enterprise_source_bundle,
        )

        snapshot = load_enterprise_source_bundle(ENTERPRISE_MANIFEST)[
            "source_snapshot"
        ]
        duplicate_type = copy.deepcopy(snapshot)
        type_record = next(
            record
            for record in duplicate_type["records"]
            if record["source_record_id"] == "inventory-lot-017-type"
        )
        duplicate_type["records"].append(
            {
                **type_record,
                "source_record_id": "inventory-type-duplicate-017",
                "evidence_ref": "wms:inventory-type-duplicate-017",
            }
        )
        with self.assertRaisesRegex(
            investigation.InvestigationScopeError, "one object type"
        ):
            investigation.evaluate_control_scope(
                duplicate_type, quality_signal_id="quality-event-017"
            )

    def test_abnormal_and_normal_records_produce_prioritized_factors_and_counterevidence(self):
        investigation = investigation_module()

        result = investigation.evaluate_investigation_scope(
            source_snapshot(),
            quality_signal_id="quality-event-017",
            factor_predicates=FACTOR_PREDICATES,
        )

        self.assertEqual(result.schema, "investigation_scope.v1")
        self.assertEqual(result.quality_signal_id, "quality-event-017")
        self.assertEqual(
            tuple(
                (factor.status.value, factor.predicate, factor.factor_id)
                for factor in result.factors
            ),
            (
                ("priority", "EXECUTED_ON", "equipment-e07"),
                ("priority", "USES_BATCH", "component-batch-017"),
                ("weakened", "BUILT_UNDER_VERSION", "process-version-v3"),
            ),
        )

        process_version = result.factors[2]
        self.assertEqual(
            process_version.evidence_refs,
            ("mes:process-version-abnormal-017",),
        )
        self.assertEqual(
            process_version.counterevidence_refs,
            ("mes:process-version-normal-021",),
        )
        self.assertFalse(result.root_cause_confirmed)

    def test_missing_source_link_remains_an_explicit_gap(self):
        investigation = investigation_module()

        result = investigation.evaluate_investigation_scope(
            source_snapshot(),
            quality_signal_id="quality-event-017",
            factor_predicates=FACTOR_PREDICATES,
        )

        self.assertEqual(len(result.gaps), 1)
        gap = result.gaps[0]
        self.assertEqual(gap.subject_id, "unit-abnormal-017-a")
        self.assertEqual(gap.predicate, "MAPPED_TO_PROJECT")
        self.assertEqual(gap.source_system, "PLM_SYNTHETIC")
        self.assertEqual(
            gap.evidence_ref,
            "plm:missing-project-product-map-017",
        )

    def test_record_order_does_not_change_the_result(self):
        investigation = investigation_module()
        snapshot = source_snapshot()

        forward = investigation.evaluate_investigation_scope(
            snapshot,
            quality_signal_id="quality-event-017",
            factor_predicates=FACTOR_PREDICATES,
        )
        reversed_snapshot = {
            **snapshot,
            "records": list(reversed(snapshot["records"])),
        }
        backward = investigation.evaluate_investigation_scope(
            reversed_snapshot,
            quality_signal_id="quality-event-017",
            factor_predicates=tuple(reversed(FACTOR_PREDICATES)),
        )

        self.assertEqual(forward, backward)

    def test_duplicate_source_record_ids_are_rejected(self):
        investigation = investigation_module()
        snapshot = source_snapshot()
        duplicate = {**snapshot, "records": [*snapshot["records"], snapshot["records"][0]]}

        with self.assertRaisesRegex(
            investigation.InvestigationScopeError,
            "source_record_id",
        ):
            investigation.evaluate_investigation_scope(
                duplicate,
                quality_signal_id="quality-event-017",
                factor_predicates=FACTOR_PREDICATES,
            )

    def test_source_snapshot_contains_no_computed_answer_or_non_synthetic_scope(self):
        raw = SNAPSHOT_PATH.read_text(encoding="utf-8")

        self.assertNotRegex(
            raw,
            r'"(?:status|priority|root_cause|confirmed|possible|excluded|not_evaluable)"',
        )
        self.assertNotIn("customer_data", raw)


if __name__ == "__main__":
    unittest.main()

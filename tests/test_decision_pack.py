import dataclasses
import hashlib
import json
import unittest

from ontology_poc_generator.decision_pack import (
    DecisionPack,
    InputBinding,
    decision_pack_content_hash,
    decision_pack_to_dict,
    render_decision_pack_json,
)
from ontology_poc_generator.errors import KnowledgeValidationError
from ontology_poc_generator.models import ScenarioParameters
from ontology_poc_generator.knowledge import (
    KnowledgeOutcome,
    KnowledgeSuggestion,
    MatchStatus,
)
from ontology_poc_generator.knowledge import SourceKind, SourceRef


def minimal_scenario(**overrides):
    data = {
        "industry": "供应链",
        "scene_name": "订单干预",
        "business_decision": "哪些订单进入优先干预队列",
        "decision_owner": "计划经理",
        "trigger": "订单承诺变化",
        "objects": ["订单", "物料", "供应商"],
        "acceptance_questions": ["结论可解释吗？"],
        "decision_key": "order_priority_intervention",
        "object_role_bindings": [
            {"role_key": "customer_order", "semantic_key": "order.primary", "object_label": "订单"},
            {"role_key": "material", "semantic_key": "material.required", "object_label": "物料"},
            {"role_key": "supplier", "semantic_key": "supplier.candidate", "object_label": "供应商"},
        ],
        "declared_bridges": [
            {"semantic_key": "customer_order_requires_material", "source_role_key": "customer_order", "predicate": "REQUIRES", "target_role_key": "material"}
        ],
    }
    data.update(overrides)
    return ScenarioParameters.from_dict(data)


def legacy_scenario():
    return ScenarioParameters.from_dict({
        "industry": "供应链",
        "scene_name": "订单干预",
        "business_decision": "选择订单",
        "decision_owner": "计划经理",
        "trigger": "承诺变化",
        "objects": ["订单", "物料"],
        "acceptance_questions": ["可解释吗？"],
    })


class DecisionPackTest(unittest.TestCase):
    def test_value_objects_are_frozen(self):
        binding = InputBinding("binding_1", "customer_order", "order.primary", "订单")
        outcome = KnowledgeOutcome(
            "unit", "1.0.0", "0" * 64, MatchStatus.NOT_APPLICABLE,
            "decision_mismatch", (), (),
        )
        pack = DecisionPack("decision_pack.v1", legacy_scenario(), (), (), (outcome,))

        with self.assertRaises(dataclasses.FrozenInstanceError):
            binding.label = "改名"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            pack.schema = "changed"
        with self.assertRaises(dataclasses.FrozenInstanceError):
            outcome.reason_code = "changed"

    def test_canonical_serialization_is_stable_and_has_no_lifecycle_or_result_fields(self):
        pack = DecisionPack("decision_pack.v1", legacy_scenario(), (), (), ())

        first = render_decision_pack_json(pack)
        second = render_decision_pack_json(pack)

        self.assertEqual(first, second)
        self.assertEqual(
            decision_pack_content_hash(pack),
            hashlib.sha256(first.encode("utf-8")).hexdigest(),
        )
        self.assertEqual(json.loads(first), decision_pack_to_dict(pack))
        forbidden = {
            "version", "base", "review", "publication", "facts", "receipt",
            "action", "rule_result", "validation_receipt",
        }
        self.assertTrue(forbidden.isdisjoint(json.loads(first)))

    def test_pack_rejects_unknown_schema_and_duplicate_aggregate_ids(self):
        source = SourceRef(
            "source", SourceKind.PRACTITIONER_NOTE, "Title", "local", "1",
            "0" * 64, "Caveat.",
        )
        outcome = KnowledgeOutcome(
            "unit", "1.0.0", "0" * 64, MatchStatus.NOT_APPLICABLE,
            "decision_mismatch", (), (),
        )

        with self.assertRaisesRegex(KnowledgeValidationError, "schema must equal decision_pack.v1"):
            DecisionPack("other.v1", legacy_scenario(), (), (), ())
        with self.assertRaisesRegex(KnowledgeValidationError, "duplicate binding_id"):
            binding = InputBinding("same", "role", "entity", "Entity")
            DecisionPack("decision_pack.v1", legacy_scenario(), (binding, binding), (), ())
        with self.assertRaisesRegex(KnowledgeValidationError, "duplicate source_ref_id"):
            DecisionPack("decision_pack.v1", legacy_scenario(), (), (source, source), ())
        with self.assertRaisesRegex(KnowledgeValidationError, "duplicate outcome unit_id"):
            DecisionPack("decision_pack.v1", legacy_scenario(), (), (), (outcome, outcome))

    def test_pack_rejects_bindings_that_do_not_exactly_match_scenario(self):
        with self.assertRaisesRegex(KnowledgeValidationError, "input_bindings must match scenario"):
            DecisionPack("decision_pack.v1", minimal_scenario(), (), (), ())

    def test_pack_rejects_foreign_outcome_binding_and_imprecise_source_catalog(self):
        outcome = KnowledgeOutcome(
            "unit", "1.0.0", "0" * 64, MatchStatus.NOT_APPLICABLE,
            "decision_mismatch", ("foreign",), (),
        )
        unused = SourceRef(
            "unused", SourceKind.PRACTITIONER_NOTE, "Title", "local", "1",
            "0" * 64, "Caveat.",
        )

        with self.assertRaisesRegex(KnowledgeValidationError, "outcome references binding outside pack"):
            DecisionPack("decision_pack.v1", legacy_scenario(), (), (), (outcome,))
        with self.assertRaisesRegex(KnowledgeValidationError, "source catalog must exactly match"):
            DecisionPack("decision_pack.v1", legacy_scenario(), (), (unused,), ())

    def test_pack_rejects_duplicate_suggestion_id_across_outcomes(self):
        source = SourceRef(
            "source", SourceKind.PRACTITIONER_NOTE, "Title", "local", "1",
            "0" * 64, "Caveat.",
        )

        def outcome(unit_id, content_hash):
            suggestion = KnowledgeSuggestion(
                "same-suggestion-id", unit_id, "1.0.0", content_hash,
                "constraint", "candidate_constraint",
                (("description", "Candidate only."),), (), ("source",),
                payload_schema="constraint.narrative.v1",
            )
            return KnowledgeOutcome(
                unit_id, "1.0.0", content_hash, MatchStatus.APPLICABLE,
                "applicable", (), (suggestion,),
            )

        with self.assertRaisesRegex(
            KnowledgeValidationError, "duplicate suggestion_id across outcomes"
        ):
            DecisionPack(
                "decision_pack.v1", legacy_scenario(), (), (source,),
                (outcome("unit.one", "1" * 64), outcome("unit.two", "2" * 64)),
            )


if __name__ == "__main__":
    unittest.main()

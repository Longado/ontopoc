from dataclasses import FrozenInstanceError
from pathlib import Path
import unittest

from ontology_poc_generator.errors import KnowledgeValidationError, ScenarioValidationError
from ontology_poc_generator.identity import stable_binding_id
from ontology_poc_generator.knowledge import (
    ApplicabilitySpec,
    KnowledgeOutcome,
    KnowledgeSuggestion,
    KnowledgeUnit,
    MatchStatus,
    RequiredBridge,
    SourceKind,
    SourceRef,
    load_knowledge_unit,
    match_knowledge_unit,
)
from ontology_poc_generator.models import (
    DeclaredBridge,
    ObjectRoleBinding,
    ReadinessDeclaration,
    ReadinessStatus,
    ScenarioParameters,
)


VALID_HASH = "a" * 64
UNIT_PATH = (
    Path(__file__).parents[1]
    / "knowledge/supply_chain/supplier_evidence_boundary_v1.json"
)


def scenario_dict() -> dict:
    return {
        "industry": "制造业供应链",
        "scene_name": "履约风险",
        "business_decision": "哪些订单进入优先干预队列",
        "decision_key": "order_priority_intervention",
        "decision_owner": "计划经理",
        "trigger": "承诺变化时",
        "objects": ["客户订单", "物料", "供应商"],
        "acceptance_questions": ["能否解释？"],
        "object_role_bindings": [
            {
                "role_key": "customer_order",
                "semantic_key": "order.primary",
                "object_label": "客户订单",
            },
            {
                "role_key": "material",
                "semantic_key": "material.required",
                "object_label": "物料",
            },
            {
                "role_key": "supplier",
                "semantic_key": "supplier.candidate",
                "object_label": "供应商",
            },
        ],
        "declared_bridges": [
            {
                "semantic_key": "customer_order_requires_material",
                "source_role_key": "customer_order",
                "predicate": "REQUIRES",
                "target_role_key": "material",
            }
        ],
        "readiness_declarations": [
            {
                "requirement_key": "queue_entry_evidence_policy",
                "status": "to_confirm",
            }
        ],
    }


class SemanticIntakeTest(unittest.TestCase):
    def test_contracts_are_frozen_and_tuple_backed(self):
        params = ScenarioParameters.from_dict(scenario_dict())

        self.assertIsInstance(params.object_role_bindings, tuple)
        self.assertIsInstance(params.declared_bridges, tuple)
        self.assertIsInstance(params.readiness_declarations, tuple)
        with self.assertRaises(FrozenInstanceError):
            params.object_role_bindings[0].object_label = "改名"

    def test_legacy_json_defaults_remain_empty(self):
        data = scenario_dict()
        for key in (
            "decision_key",
            "object_role_bindings",
            "declared_bridges",
            "readiness_declarations",
        ):
            data.pop(key, None)

        params = ScenarioParameters.from_dict(data)

        self.assertEqual(params.decision_key, "")
        self.assertEqual(params.object_role_bindings, ())
        self.assertEqual(params.declared_bridges, ())
        self.assertEqual(params.readiness_declarations, ())

    def test_roles_may_share_a_semantic_key_because_role_is_part_of_identity(self):
        data = scenario_dict()
        data["object_role_bindings"][1]["semantic_key"] = "order.primary"

        params = ScenarioParameters.from_dict(data)
        binding_ids = {
            item.role_key: stable_binding_id(
                params.decision_key, item.role_key, item.semantic_key
            )
            for item in params.object_role_bindings
        }

        self.assertNotEqual(
            binding_ids["customer_order"], binding_ids["material"]
        )

    def test_rejects_non_tuple_direct_semantic_fields(self):
        base = dict(
            industry="供应链",
            scene_name="履约风险",
            business_decision="哪些订单进入优先干预队列",
            decision_owner="计划经理",
            trigger="承诺变化时",
            objects=("客户订单", "物料"),
            acceptance_questions=("能否解释？",),
        )
        for field, value in (
            ("object_role_bindings", []),
            ("declared_bridges", []),
            ("readiness_declarations", []),
        ):
            with self.subTest(field=field), self.assertRaisesRegex(
                ScenarioValidationError, f"{field} must be a tuple"
            ):
                ScenarioParameters(**base, **{field: value})

    def test_rejects_malformed_or_duplicate_semantic_inputs(self):
        cases = []
        bad = scenario_dict()
        bad["object_role_bindings"][0]["role_key"] = "Customer Order"
        cases.append((bad, "role_key"))
        bad = scenario_dict()
        bad["object_role_bindings"].append(dict(bad["object_role_bindings"][0]))
        cases.append((bad, "duplicate object role"))
        bad = scenario_dict()
        bad["object_role_bindings"][0]["object_label"] = "不存在"
        cases.append((bad, "must reference an object"))
        bad = scenario_dict()
        bad["declared_bridges"][0]["target_role_key"] = "warehouse"
        cases.append((bad, "unknown role"))
        bad = scenario_dict()
        bad["declared_bridges"].append(dict(bad["declared_bridges"][0]))
        cases.append((bad, "duplicate declared bridge"))
        bad = scenario_dict()
        bad["readiness_declarations"][0]["status"] = "pending"
        cases.append((bad, "status must be ready, to_confirm, or unavailable"))
        bad = scenario_dict()
        bad["readiness_declarations"].append(
            dict(bad["readiness_declarations"][0])
        )
        cases.append((bad, "duplicate readiness declaration"))

        for data, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ScenarioValidationError, message
            ):
                ScenarioParameters.from_dict(data)


class KnowledgeMatchingTest(unittest.TestCase):
    def setUp(self):
        self.unit = load_knowledge_unit(UNIT_PATH)

    def test_unit_rejects_template_binding_without_declared_role(self):
        template = self.unit.suggestion_templates[0]

        with self.assertRaisesRegex(
            KnowledgeValidationError,
            "template references unknown applicability role",
        ):
            KnowledgeUnit(
                unit_id=self.unit.unit_id,
                unit_version=self.unit.unit_version,
                decision_key=self.unit.decision_key,
                unit_content_hash=self.unit.unit_content_hash,
                source_refs=self.unit.source_refs,
                suggestion_templates=(template,),
                applicability=ApplicabilitySpec(),
            )

    def test_non_applicable_outcome_cannot_carry_suggestions(self):
        with self.assertRaisesRegex(
            KnowledgeValidationError,
            "non-applicable outcome cannot carry suggestions",
        ):
            KnowledgeOutcome(
                unit_id=self.unit.unit_id,
                unit_version=self.unit.unit_version,
                unit_content_hash=self.unit.unit_content_hash,
                match_status=MatchStatus.NOT_APPLICABLE,
                reason_code="decision_key_mismatch",
                input_binding_ids=(),
                suggestions=(self.unit.suggestion_templates[0],),
            )

    def test_insufficient_outcome_may_preserve_partial_bindings_only(self):
        outcome = KnowledgeOutcome(
            unit_id=self.unit.unit_id,
            unit_version=self.unit.unit_version,
            unit_content_hash=self.unit.unit_content_hash,
            match_status=MatchStatus.INSUFFICIENT_INFORMATION,
            reason_code="required_role_missing",
            input_binding_ids=("binding_partial",),
            suggestions=(),
        )

        self.assertEqual(outcome.input_binding_ids, ("binding_partial",))

    def test_applicable_outcome_rejects_provenance_mismatch_and_duplicate_ids(self):
        first = self.unit.suggestion_templates[0]
        mismatch = KnowledgeSuggestion(
            suggestion_id="mismatch",
            unit_id="other.unit",
            unit_version=first.unit_version,
            unit_content_hash=first.unit_content_hash,
            contribution_type=first.contribution_type,
            semantic_key=first.semantic_key,
            payload=first.payload,
            input_binding_ids=first.input_binding_ids,
            source_ref_ids=first.source_ref_ids,
        )
        for suggestions, message in (
            ((mismatch,), "suggestion provenance must match outcome"),
            ((first, first), "suggestion_id must be unique"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(
                KnowledgeValidationError, message
            ):
                KnowledgeOutcome(
                    unit_id=self.unit.unit_id,
                    unit_version=self.unit.unit_version,
                    unit_content_hash=self.unit.unit_content_hash,
                    match_status=MatchStatus.APPLICABLE,
                    reason_code="applicable",
                    input_binding_ids=(),
                    suggestions=suggestions,
                )

    def test_matching_semantics_are_applicable_and_bind_templates(self):
        params = ScenarioParameters.from_dict(scenario_dict())

        outcome = match_knowledge_unit(params, self.unit)

        self.assertEqual(outcome.match_status, MatchStatus.APPLICABLE)
        self.assertEqual(outcome.reason_code, "applicable")
        self.assertEqual(len(outcome.input_binding_ids), 3)
        self.assertEqual(len(outcome.suggestions), 7)
        role_bindings = {
            item.role_key: stable_binding_id(
                params.decision_key, item.role_key, item.semantic_key
            )
            for item in params.object_role_bindings
        }
        qualified = outcome.suggestions[0]
        self.assertEqual(
            qualified.input_binding_ids,
            (role_bindings["supplier"], role_bindings["material"]),
        )
        self.assertNotEqual(qualified.suggestion_id, "relation.qualified_to_supply")
        self.assertEqual(
            tuple(item.contribution_type for item in outcome.suggestions)[-1],
            "readiness_gap",
        )

    def test_non_ready_readiness_keeps_gap_but_ready_filters_it(self):
        missing = scenario_dict()
        missing["readiness_declarations"] = []
        unavailable = scenario_dict()
        unavailable["readiness_declarations"][0]["status"] = "unavailable"
        ready = scenario_dict()
        ready["readiness_declarations"][0]["status"] = "ready"

        for data in (missing, scenario_dict(), unavailable):
            with self.subTest(status=data.get("readiness_declarations")):
                outcome = match_knowledge_unit(
                    ScenarioParameters.from_dict(data), self.unit
                )
                self.assertIn(
                    "readiness_gap",
                    tuple(item.contribution_type for item in outcome.suggestions),
                )
        outcome = match_knowledge_unit(ScenarioParameters.from_dict(ready), self.unit)
        self.assertNotIn(
            "readiness_gap",
            tuple(item.contribution_type for item in outcome.suggestions),
        )

    def test_decision_mismatch_is_not_applicable_without_suggestions(self):
        data = scenario_dict()
        data["decision_key"] = "dairy_experiment_selection"

        outcome = match_knowledge_unit(ScenarioParameters.from_dict(data), self.unit)

        self.assertEqual(outcome.match_status, MatchStatus.NOT_APPLICABLE)
        self.assertEqual(outcome.reason_code, "decision_key_mismatch")
        self.assertEqual(outcome.suggestions, ())

    def test_missing_role_or_bridge_is_insufficient_without_suggestions(self):
        missing_role = scenario_dict()
        missing_role["object_role_bindings"] = missing_role["object_role_bindings"][:-1]
        missing_bridge = scenario_dict()
        missing_bridge["declared_bridges"] = []
        wrong_bridge = scenario_dict()
        wrong_bridge["declared_bridges"][0]["predicate"] = "CONTAINS"

        role_outcome = match_knowledge_unit(
            ScenarioParameters.from_dict(missing_role), self.unit
        )
        bridge_outcome = match_knowledge_unit(
            ScenarioParameters.from_dict(missing_bridge), self.unit
        )
        wrong_bridge_outcome = match_knowledge_unit(
            ScenarioParameters.from_dict(wrong_bridge), self.unit
        )

        self.assertEqual(
            role_outcome.match_status, MatchStatus.INSUFFICIENT_INFORMATION
        )
        self.assertEqual(role_outcome.reason_code, "required_role_missing")
        self.assertEqual(role_outcome.suggestions, ())
        self.assertEqual(
            bridge_outcome.match_status, MatchStatus.INSUFFICIENT_INFORMATION
        )
        self.assertEqual(bridge_outcome.reason_code, "order_material_bridge_missing")
        self.assertEqual(bridge_outcome.suggestions, ())
        self.assertEqual(
            wrong_bridge_outcome.match_status,
            MatchStatus.INSUFFICIENT_INFORMATION,
        )
        self.assertEqual(wrong_bridge_outcome.suggestions, ())

    def test_label_and_input_order_do_not_change_ids_or_suggestions(self):
        first_data = scenario_dict()
        second_data = scenario_dict()
        second_data["objects"] = ["供方", "订单", "物资"]
        labels = {
            "customer_order": "订单",
            "material": "物资",
            "supplier": "供方",
        }
        second_data["object_role_bindings"] = list(
            reversed(second_data["object_role_bindings"])
        )
        for item in second_data["object_role_bindings"]:
            item["object_label"] = labels[item["role_key"]]

        first = match_knowledge_unit(
            ScenarioParameters.from_dict(first_data), self.unit
        )
        second = match_knowledge_unit(
            ScenarioParameters.from_dict(second_data), self.unit
        )

        self.assertEqual(first.input_binding_ids, second.input_binding_ids)
        self.assertEqual(first.suggestions, second.suggestions)

    def test_generic_declarative_unit_uses_no_industry_or_label_branch(self):
        source = SourceRef(
            "generic-source",
            SourceKind.PRACTITIONER_NOTE,
            "Generic source",
            "local/test",
            "1",
            VALID_HASH,
            "Test-only source.",
        )
        template = KnowledgeSuggestion(
            "generic.template",
            "generic.unit",
            "1.0.0",
            VALID_HASH,
            "constraint",
            "generic_constraint",
            (("description", "Generic constraint."),),
            ("alpha", "beta"),
            ("generic-source",),
        )
        unit = KnowledgeUnit(
            "generic.unit",
            "1.0.0",
            "generic_decision",
            VALID_HASH,
            (source,),
            (template,),
            ApplicabilitySpec(
                required_role_keys=("alpha", "beta"),
                required_bridges=(
                    RequiredBridge("alpha_links_beta", "alpha", "LINKS", "beta"),
                ),
                decision_mismatch_reason_code="wrong_decision",
                missing_required_role_reason_code="missing_alias",
                missing_required_bridge_reason_code="missing_link",
            ),
        )
        data = scenario_dict()
        data.update(
            {
                "industry": "任意领域",
                "business_decision": "完全不同的展示文案",
                "decision_key": "generic_decision",
                "objects": ["甲", "乙"],
                "object_role_bindings": [
                    {
                        "role_key": "alpha",
                        "semantic_key": "entity.a",
                        "object_label": "甲",
                    },
                    {
                        "role_key": "beta",
                        "semantic_key": "entity.b",
                        "object_label": "乙",
                    },
                ],
                "declared_bridges": [
                    {
                        "semantic_key": "alpha_links_beta",
                        "source_role_key": "alpha",
                        "predicate": "LINKS",
                        "target_role_key": "beta",
                    }
                ],
                "readiness_declarations": [],
            }
        )

        outcome = match_knowledge_unit(ScenarioParameters.from_dict(data), unit)

        self.assertEqual(outcome.match_status, MatchStatus.APPLICABLE)
        self.assertEqual(len(outcome.suggestions), 1)


if __name__ == "__main__":
    unittest.main()

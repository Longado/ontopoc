import dataclasses
import unittest
from pathlib import Path

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.errors import SpecCompilationError
from ontology_poc_generator.identity import (
    stable_entity_type_id,
    stable_suggestion_id,
)
from ontology_poc_generator.knowledge import (
    KnowledgeOutcome,
    MatchStatus,
    load_knowledge_unit,
)
from ontology_poc_generator.knowledge_compiler import (
    KnowledgeCompilation,
    compile_knowledge_profiles,
)
from ontology_poc_generator.ontology_spec import (
    CompilationIssueSeverity,
    EntityTypeSpec,
    SpecGovernanceStatus,
    SpecOriginKind,
)
from tests.test_decision_pack import minimal_scenario


ROOT = Path(__file__).parents[1]
UNIT_PATH = ROOT / "knowledge/supply_chain/supplier_evidence_boundary_v1.json"


def entity_types_for(pack):
    return tuple(
        EntityTypeSpec(
            type_id=stable_entity_type_id(
                pack.scenario.decision_key,
                binding.role_key,
                binding.semantic_key,
            ),
            role_key=binding.role_key,
            semantic_key=binding.semantic_key,
            label=binding.label,
            governance_status=SpecGovernanceStatus.CANDIDATE,
            origin_kind=SpecOriginKind.PROVIDED_INPUT,
            origin_ref_id=binding.binding_id,
        )
        for binding in pack.input_bindings
    )


def pack_with_outcomes(pack, outcomes):
    cited_source_ids = {
        source_ref_id
        for outcome in outcomes
        for suggestion in outcome.suggestions
        for source_ref_id in suggestion.source_ref_ids
    }
    return dataclasses.replace(
        pack,
        source_refs=tuple(
            source
            for source in pack.source_refs
            if source.source_ref_id in cited_source_ids
        ),
        knowledge_outcomes=outcomes,
    )


class KnowledgeCompilerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.unit = load_knowledge_unit(UNIT_PATH)

    def golden_pack(self, **scenario_overrides):
        return compile_decision_pack(
            minimal_scenario(**scenario_overrides),
            (self.unit,),
        )

    def test_golden_profiles_compile_two_relations_and_five_bound_issues(self):
        pack = self.golden_pack()

        result = compile_knowledge_profiles(pack, entity_types_for(pack))

        self.assertIsInstance(result, KnowledgeCompilation)
        self.assertEqual(
            {relation.predicate for relation in result.relation_types},
            {"QUALIFIED_TO_SUPPLY", "HAS_SUPPLIED"},
        )
        self.assertNotIn(
            "SUPPLIES", {relation.predicate for relation in result.relation_types}
        )
        self.assertEqual(len(result.compilation_issues), 5)
        self.assertEqual(
            [issue.payload_schema for issue in result.compilation_issues].count(
                "data_requirement.narrative.v1"
            ),
            2,
        )
        expected_codes = {
            "narrative_constraint_requires_formalization",
            "data_requirement_not_executable",
            "acceptance_question_not_executable",
            "readiness_gap_blocks_rule_compilation",
        }
        self.assertEqual(
            {issue.code for issue in result.compilation_issues}, expected_codes
        )
        self.assertTrue(
            all(
                issue.severity is CompilationIssueSeverity.REQUIRES_REVIEW
                for issue in result.compilation_issues
            )
        )
        suggestion_ids = {
            suggestion.suggestion_id
            for outcome in pack.knowledge_outcomes
            for suggestion in outcome.suggestions
        }
        accounted_ids = {
            relation.origin_ref_id for relation in result.relation_types
        } | {issue.suggestion_id for issue in result.compilation_issues}
        self.assertEqual(accounted_ids, suggestion_ids)
        self.assertEqual(result.property_types, ())
        self.assertEqual(result.rule_declarations, ())

    def test_relation_endpoints_follow_role_binding_to_entity_type(self):
        pack = self.golden_pack()
        entities = entity_types_for(pack)
        entities_by_id = {entity.type_id: entity for entity in entities}

        result = compile_knowledge_profiles(pack, entities)

        for relation in result.relation_types:
            self.assertEqual(
                entities_by_id[relation.domain_type_id].role_key, "supplier"
            )
            self.assertEqual(
                entities_by_id[relation.range_type_id].role_key, "material"
            )
            self.assertIs(
                relation.origin_kind, SpecOriginKind.KNOWLEDGE_SUGGESTION
            )

    def test_reordering_and_display_label_rename_keep_compiled_identities(self):
        first_pack = self.golden_pack()
        renamed_pack = self.golden_pack(
            objects=["客户单", "物资", "供方"],
            object_role_bindings=[
                {
                    "role_key": "supplier",
                    "semantic_key": "supplier.candidate",
                    "object_label": "供方",
                },
                {
                    "role_key": "material",
                    "semantic_key": "material.required",
                    "object_label": "物资",
                },
                {
                    "role_key": "customer_order",
                    "semantic_key": "order.primary",
                    "object_label": "客户单",
                },
            ],
        )
        reversed_outcome = dataclasses.replace(
            renamed_pack.knowledge_outcomes[0],
            suggestions=tuple(reversed(renamed_pack.knowledge_outcomes[0].suggestions)),
        )
        renamed_pack = dataclasses.replace(
            renamed_pack, knowledge_outcomes=(reversed_outcome,)
        )

        first = compile_knowledge_profiles(
            first_pack, tuple(reversed(entity_types_for(first_pack)))
        )
        second = compile_knowledge_profiles(
            renamed_pack, tuple(reversed(entity_types_for(renamed_pack)))
        )

        self.assertEqual(
            tuple(item.relation_type_id for item in first.relation_types),
            tuple(item.relation_type_id for item in second.relation_types),
        )
        self.assertEqual(
            tuple(item.issue_id for item in first.compilation_issues),
            tuple(item.issue_id for item in second.compilation_issues),
        )

    def test_non_applicable_and_insufficient_outcomes_compile_nothing(self):
        for pack in (
            self.golden_pack(decision_key="different_decision"),
            self.golden_pack(declared_bridges=[]),
        ):
            with self.subTest(status=pack.knowledge_outcomes[0].match_status):
                result = compile_knowledge_profiles(pack, entity_types_for(pack))
                self.assertEqual(result, KnowledgeCompilation())

    def test_missing_relation_role_fails_loudly(self):
        pack = self.golden_pack()
        relation = next(
            suggestion
            for suggestion in pack.knowledge_outcomes[0].suggestions
            if suggestion.payload_schema == "relation_semantics.v1"
        )
        broken = dataclasses.replace(
            relation,
            payload=tuple(
                (key, "unknown_role" if key == "source_role_key" else value)
                for key, value in relation.payload
            ),
        )
        outcome = dataclasses.replace(
            pack.knowledge_outcomes[0],
            suggestions=(broken,),
        )
        pack = pack_with_outcomes(pack, (outcome,))

        with self.assertRaises(SpecCompilationError) as caught:
            compile_knowledge_profiles(pack, entity_types_for(pack))

        self.assertEqual(caught.exception.code, "missing_relation_role_binding")

    def test_relation_endpoint_must_be_in_suggestion_provenance(self):
        pack = self.golden_pack()
        relation = next(
            suggestion
            for suggestion in pack.knowledge_outcomes[0].suggestions
            if suggestion.payload_schema == "relation_semantics.v1"
        )
        supplier_binding = next(
            binding
            for binding in pack.input_bindings
            if binding.role_key == "supplier"
        )
        broken = dataclasses.replace(
            relation,
            input_binding_ids=tuple(
                binding_id
                for binding_id in relation.input_binding_ids
                if binding_id != supplier_binding.binding_id
            ),
        )
        outcome = dataclasses.replace(
            pack.knowledge_outcomes[0], suggestions=(broken,)
        )
        pack = pack_with_outcomes(pack, (outcome,))

        with self.assertRaises(SpecCompilationError) as caught:
            compile_knowledge_profiles(pack, entity_types_for(pack))

        self.assertEqual(
            caught.exception.code, "relation_endpoint_binding_mismatch"
        )

    def test_existing_relation_identity_collision_is_fatal(self):
        pack = self.golden_pack()
        entities = entity_types_for(pack)
        first = compile_knowledge_profiles(pack, entities).relation_types[0]
        existing = dataclasses.replace(
            first,
            origin_kind=SpecOriginKind.PROVIDED_INPUT,
            origin_ref_id="declared_bridge_collision",
        )

        with self.assertRaises(SpecCompilationError) as caught:
            compile_knowledge_profiles(
                pack, entities, existing_relation_types=(existing,)
            )

        self.assertEqual(
            caught.exception.code, "duplicate_relation_type_identity"
        )

    def test_multiple_knowledge_sources_cannot_share_relation_identity(self):
        pack = self.golden_pack()
        relation = next(
            suggestion
            for suggestion in pack.knowledge_outcomes[0].suggestions
            if suggestion.payload_schema == "relation_semantics.v1"
        )
        other_unit_id = "other.supplier_evidence"
        other_unit_hash = "1" * 64
        duplicate = dataclasses.replace(
            relation,
            suggestion_id=stable_suggestion_id(
                other_unit_id,
                "1.0.0",
                relation.semantic_key,
                relation.input_binding_ids,
            ),
            unit_id=other_unit_id,
            unit_version="1.0.0",
            unit_content_hash=other_unit_hash,
        )
        duplicate_outcome = KnowledgeOutcome(
            unit_id=other_unit_id,
            unit_version="1.0.0",
            unit_content_hash=other_unit_hash,
            match_status=MatchStatus.APPLICABLE,
            reason_code="matched",
            input_binding_ids=relation.input_binding_ids,
            suggestions=(duplicate,),
        )
        original_outcome = dataclasses.replace(
            pack.knowledge_outcomes[0], suggestions=(relation,)
        )
        pack = pack_with_outcomes(
            pack, (original_outcome, duplicate_outcome)
        )

        with self.assertRaises(SpecCompilationError) as caught:
            compile_knowledge_profiles(pack, entity_types_for(pack))

        self.assertEqual(
            caught.exception.code, "duplicate_relation_type_identity"
        )

    def test_readiness_profile_never_becomes_a_rule(self):
        pack = self.golden_pack()

        result = compile_knowledge_profiles(pack, entity_types_for(pack))

        self.assertEqual(result.rule_declarations, ())
        self.assertIn(
            "readiness_gap_blocks_rule_compilation",
            {issue.code for issue in result.compilation_issues},
        )


if __name__ == "__main__":
    unittest.main()

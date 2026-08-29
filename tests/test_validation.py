from dataclasses import FrozenInstanceError, replace
from pathlib import Path
import unittest

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.decision_pack import DecisionPack, decision_pack_content_hash
from ontology_poc_generator.errors import (
    OntologySpecValidationError,
    SpecCompilationError,
)
from ontology_poc_generator.identity import (
    stable_closure_issue_id,
    stable_compilation_issue_id,
    stable_entity_type_id,
    stable_relation_type_id,
)
from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.ontology_spec import (
    ClosureIssue,
    CompilationIssue,
    CompilationIssueSeverity,
    CompilationStatus,
    EntityTypeSpec,
    EvidenceScope,
    OntologySpec,
    PropertyTypeSpec,
    ReferenceClosureReport,
    RelationTypeSpec,
    RuleConditionSpec,
    RuleDeclarationSpec,
    SpecCompilationResult,
    SpecGovernanceStatus,
    SpecOriginKind,
    SpecStage,
    ontology_spec_content_hash,
)
from ontology_poc_generator.validation import validate_reference_closure
from tests.test_decision_pack import minimal_scenario


VALID_HASH = "a" * 64
ROOT = Path(__file__).parents[1]
UNIT_PATH = ROOT / "knowledge/supply_chain/supplier_evidence_boundary_v1.json"
NON_EXECUTABLE_CODES = {
    "constraint.narrative.v1": "narrative_constraint_requires_formalization",
    "data_requirement.narrative.v1": "data_requirement_not_executable",
    "acceptance_question.v1": "acceptance_question_not_executable",
    "readiness_gap.v1": "readiness_gap_blocks_rule_compilation",
}


def empty_spec(**overrides: object) -> OntologySpec:
    values = {
        "schema": "ontology_spec.v1",
        "decision_key": "order_priority_intervention",
        "pack_content_hash": VALID_HASH,
        "stage": SpecStage.DRAFT,
        "evidence_scope": EvidenceScope.SYNTHETIC_DEMO,
        "governance_status": SpecGovernanceStatus.CANDIDATE,
        "input_binding_ids": (),
        "entity_types": (),
        "relation_types": (),
        "property_types": (),
        "rule_declarations": (),
        "compilation_issues": (),
    }
    values.update(overrides)
    return OntologySpec(**values)


def closure_issue(
    *,
    issue_id: str = "closure_issue_1",
    code: str = "dangling_relation_domain",
) -> ClosureIssue:
    return ClosureIssue(
        issue_id=issue_id,
        code=code,
        owner_id="relation_1",
        field="domain_type_id",
        referenced_id="entity_missing",
    )


def golden_pack() -> DecisionPack:
    return compile_decision_pack(
        minimal_scenario(),
        (load_knowledge_unit(UNIT_PATH),),
    )


def golden_spec(pack: DecisionPack) -> OntologySpec:
    entities = tuple(
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
    entity_by_role = {item.role_key: item for item in entities}
    provided_relations = tuple(
        RelationTypeSpec(
            relation_type_id=stable_relation_type_id(
                bridge.semantic_key,
                entity_by_role[bridge.source_role_key].type_id,
                bridge.predicate,
                entity_by_role[bridge.target_role_key].type_id,
            ),
            semantic_key=bridge.semantic_key,
            predicate=bridge.predicate,
            domain_type_id=entity_by_role[bridge.source_role_key].type_id,
            range_type_id=entity_by_role[bridge.target_role_key].type_id,
            description="Provided relation.",
            governance_status=SpecGovernanceStatus.CANDIDATE,
            origin_kind=SpecOriginKind.PROVIDED_INPUT,
            origin_ref_id=bridge.semantic_key,
        )
        for bridge in pack.scenario.declared_bridges
    )
    knowledge_relations = []
    compilation_issues = []
    for outcome in pack.knowledge_outcomes:
        for suggestion in outcome.suggestions:
            payload = dict(suggestion.payload)
            if suggestion.payload_schema == "relation_semantics.v1":
                domain = entity_by_role[payload["source_role_key"]]
                range_ = entity_by_role[payload["target_role_key"]]
                knowledge_relations.append(
                    RelationTypeSpec(
                        relation_type_id=stable_relation_type_id(
                            suggestion.semantic_key,
                            domain.type_id,
                            payload["predicate"],
                            range_.type_id,
                        ),
                        semantic_key=suggestion.semantic_key,
                        predicate=payload["predicate"],
                        domain_type_id=domain.type_id,
                        range_type_id=range_.type_id,
                        description=payload["description"],
                        governance_status=SpecGovernanceStatus.CANDIDATE,
                        origin_kind=SpecOriginKind.KNOWLEDGE_SUGGESTION,
                        origin_ref_id=suggestion.suggestion_id,
                    )
                )
            else:
                code = NON_EXECUTABLE_CODES[suggestion.payload_schema]
                compilation_issues.append(
                    CompilationIssue(
                        issue_id=stable_compilation_issue_id(
                            suggestion.suggestion_id,
                            code,
                            suggestion.payload_schema,
                        ),
                        code=code,
                        severity=CompilationIssueSeverity.REQUIRES_REVIEW,
                        suggestion_id=suggestion.suggestion_id,
                        payload_schema=suggestion.payload_schema,
                        message="Suggestion requires formalization.",
                    )
                )
    return OntologySpec(
        schema="ontology_spec.v1",
        decision_key=pack.scenario.decision_key,
        pack_content_hash=decision_pack_content_hash(pack),
        stage=SpecStage.DRAFT,
        evidence_scope=EvidenceScope.SYNTHETIC_DEMO,
        governance_status=SpecGovernanceStatus.CANDIDATE,
        input_binding_ids=tuple(item.binding_id for item in pack.input_bindings),
        entity_types=entities,
        relation_types=provided_relations + tuple(knowledge_relations),
        property_types=(),
        rule_declarations=(),
        compilation_issues=tuple(compilation_issues),
    )


def all_suggestions(pack: DecisionPack):
    return tuple(
        suggestion
        for outcome in pack.knowledge_outcomes
        for suggestion in outcome.suggestions
    )


class ClosureContractTest(unittest.TestCase):
    def test_closure_issue_identity_is_stable_and_field_sensitive(self):
        first = stable_closure_issue_id(
            "dangling_relation_domain",
            "relation_1",
            "domain_type_id",
            "entity_missing",
        )
        repeated = stable_closure_issue_id(
            "dangling_relation_domain",
            "relation_1",
            "domain_type_id",
            "entity_missing",
        )
        changed = stable_closure_issue_id(
            "dangling_relation_domain",
            "relation_1",
            "range_type_id",
            "entity_missing",
        )

        self.assertEqual(first, repeated)
        self.assertTrue(first.startswith("closure_issue_"))
        self.assertNotEqual(first, changed)

    def test_report_derives_is_closed_and_sorts_issues(self):
        report = ReferenceClosureReport(
            checked_reference_count=2,
            issues=(
                closure_issue(issue_id="closure_issue_z"),
                closure_issue(issue_id="closure_issue_a"),
            ),
        )

        self.assertFalse(report.is_closed)
        self.assertEqual(
            tuple(item.issue_id for item in report.issues),
            ("closure_issue_a", "closure_issue_z"),
        )
        with self.assertRaises(FrozenInstanceError):
            report.issues = ()

    def test_checked_reference_count_rejects_bool_and_negative_values(self):
        for invalid in (True, -1, 1.5):
            with self.subTest(invalid=invalid), self.assertRaises(
                OntologySpecValidationError
            ):
                ReferenceClosureReport(
                    checked_reference_count=invalid,
                    issues=(),
                )

    def test_result_derives_hash_and_complete_status(self):
        spec = empty_spec()
        result = SpecCompilationResult(
            spec=spec,
            closure_report=ReferenceClosureReport(0, ()),
        )

        self.assertEqual(result.spec_content_hash, ontology_spec_content_hash(spec))
        self.assertEqual(result.compilation_status, CompilationStatus.COMPLETE)

    def test_result_derives_blocked_status_without_mutating_spec(self):
        issue = CompilationIssue(
            issue_id="compilation_issue_blocking",
            code="unsupported_rule_kind",
            severity=CompilationIssueSeverity.BLOCKING,
            suggestion_id="suggestion_rule",
            payload_schema="decision_rule.v1",
            message="Rule kind is unsupported.",
        )
        spec = empty_spec(compilation_issues=(issue,))

        result = SpecCompilationResult(
            spec=spec,
            closure_report=ReferenceClosureReport(0, ()),
        )

        self.assertEqual(result.compilation_status, CompilationStatus.BLOCKED)
        self.assertEqual(result.spec_content_hash, ontology_spec_content_hash(spec))

    def test_open_report_cannot_form_a_result(self):
        with self.assertRaises(SpecCompilationError) as raised:
            SpecCompilationResult(
                spec=empty_spec(),
                closure_report=ReferenceClosureReport(1, (closure_issue(),)),
            )

        self.assertEqual(raised.exception.code, "compiled_spec_not_reference_closed")


class ReferenceClosureValidationTest(unittest.TestCase):
    def test_golden_spec_is_closed_and_counts_checked_references(self):
        pack = golden_pack()

        report = validate_reference_closure(golden_spec(pack), pack)

        self.assertTrue(report.is_closed)
        self.assertEqual(report.issues, ())
        self.assertGreater(report.checked_reference_count, 0)

    def test_anchor_mismatches_skip_pack_relative_noise_but_keep_internal_errors(self):
        pack = golden_pack()
        spec = golden_spec(pack)
        bad_relation = replace(
            spec.relation_types[0],
            domain_type_id="entity_missing",
            origin_ref_id="bridge_missing",
        )
        spec = replace(
            spec,
            decision_key="different_decision",
            pack_content_hash="f" * 64,
            input_binding_ids=(),
            relation_types=(bad_relation,),
            compilation_issues=(),
        )

        report = validate_reference_closure(spec, pack)
        codes = {item.code for item in report.issues}

        self.assertTrue(
            {
                "pack_content_hash_mismatch",
                "decision_key_mismatch",
                "dangling_relation_domain",
            }.issubset(codes)
        )
        self.assertTrue(
            {
                "input_binding_set_mismatch",
                "dangling_declared_bridge",
                "dangling_suggestion_reference",
                "unaccounted_suggestion",
            }.isdisjoint(codes)
        )

    def test_input_binding_ids_must_exactly_match_pack(self):
        pack = golden_pack()
        spec = replace(golden_spec(pack), input_binding_ids=())

        report = validate_reference_closure(spec, pack)

        self.assertEqual(
            sum(item.code == "input_binding_set_mismatch" for item in report.issues),
            1,
        )

    def test_collects_every_dangling_reference_without_short_circuiting(self):
        pack = golden_pack()
        base = golden_spec(pack)
        entity = replace(
            base.entity_types[0],
            origin_ref_id="binding_missing",
        )
        provided_relation = next(
            item
            for item in base.relation_types
            if item.origin_kind is SpecOriginKind.PROVIDED_INPUT
        )
        relation = replace(
            provided_relation,
            domain_type_id="entity_domain_missing",
            range_type_id="entity_range_missing",
            origin_ref_id="bridge_missing",
        )
        suggestion_id = "suggestion_missing"
        property_type = PropertyTypeSpec(
            property_type_id="property_missing_domain",
            semantic_key="order.state",
            domain_type_id="entity_property_domain_missing",
            value_type="symbolic_state",
            governance_status=SpecGovernanceStatus.CANDIDATE,
            origin_kind=SpecOriginKind.KNOWLEDGE_SUGGESTION,
            origin_ref_id=suggestion_id,
        )
        rule = RuleDeclarationSpec(
            rule_id="rule_dangling",
            semantic_key="order.queue",
            rule_kind="all_conditions_match",
            subject_type_id="entity_subject_missing",
            conditions=(
                RuleConditionSpec(
                    property_type_id="property_missing",
                    operator="in",
                    allowed_values=("at_risk",),
                ),
            ),
            output_conclusion_key="priority_queue",
            positive_conclusion_value="enter",
            negative_conclusion_value="do_not_enter",
            description="Synthetic rule.",
            governance_status=SpecGovernanceStatus.CANDIDATE,
            origin_suggestion_id=suggestion_id,
        )
        issue = CompilationIssue(
            issue_id="compilation_issue_missing",
            code="data_requirement_not_executable",
            severity=CompilationIssueSeverity.REQUIRES_REVIEW,
            suggestion_id=suggestion_id,
            payload_schema="data_requirement.narrative.v1",
            message="Missing suggestion.",
        )
        spec = replace(
            base,
            entity_types=(entity,),
            relation_types=(relation,),
            property_types=(property_type,),
            rule_declarations=(rule,),
            compilation_issues=(issue,),
        )

        report = validate_reference_closure(spec, pack)
        codes = {item.code for item in report.issues}

        self.assertTrue(
            {
                "dangling_input_binding",
                "dangling_relation_domain",
                "dangling_relation_range",
                "dangling_declared_bridge",
                "dangling_property_domain",
                "dangling_rule_subject_type",
                "dangling_rule_property",
                "dangling_suggestion_reference",
            }.issubset(codes)
        )
        self.assertNotIn("rule_property_domain_mismatch", codes)

    def test_origin_matrix_rejects_unsupported_contract_without_guessing_reference(self):
        pack = golden_pack()
        base = golden_spec(pack)
        property_type = PropertyTypeSpec(
            property_type_id="property_provided",
            semantic_key="order.state",
            domain_type_id=base.entity_types[0].type_id,
            value_type="symbolic_state",
            governance_status=SpecGovernanceStatus.CANDIDATE,
            origin_kind=SpecOriginKind.PROVIDED_INPUT,
            origin_ref_id=pack.input_bindings[0].binding_id,
        )
        spec = replace(base, property_types=(property_type,))

        report = validate_reference_closure(spec, pack)
        owner_issues = tuple(
            item for item in report.issues if item.owner_id == property_type.property_type_id
        )

        self.assertEqual(
            {item.code for item in owner_issues},
            {"unsupported_origin_contract"},
        )

    def test_origin_profiles_must_match_source_content(self):
        pack = golden_pack()
        base = golden_spec(pack)
        narrative = next(
            item
            for item in all_suggestions(pack)
            if item.payload_schema == "constraint.narrative.v1"
        )
        knowledge_relation = next(
            item
            for item in base.relation_types
            if item.origin_kind is SpecOriginKind.KNOWLEDGE_SUGGESTION
        )
        bad_relation = replace(
            knowledge_relation,
            origin_ref_id=narrative.suggestion_id,
        )
        issue = next(
            item
            for item in base.compilation_issues
            if item.suggestion_id == narrative.suggestion_id
        )
        bad_issue = replace(issue, payload_schema="acceptance_question.v1")
        spec = replace(
            base,
            relation_types=tuple(
                bad_relation if item == knowledge_relation else item
                for item in base.relation_types
            ),
            compilation_issues=tuple(
                bad_issue if item == issue else item
                for item in base.compilation_issues
            ),
        )

        report = validate_reference_closure(spec, pack)

        self.assertGreaterEqual(
            sum(item.code == "origin_profile_mismatch" for item in report.issues),
            2,
        )

    def test_rule_property_domain_must_match_subject_when_references_exist(self):
        pack = golden_pack()
        base = golden_spec(pack)
        origin = next(
            item
            for item in all_suggestions(pack)
            if item.payload_schema == "relation_semantics.v1"
        )
        first, second = base.entity_types[:2]
        property_type = PropertyTypeSpec(
            property_type_id="property_order_state",
            semantic_key="order.state",
            domain_type_id=first.type_id,
            value_type="symbolic_state",
            governance_status=SpecGovernanceStatus.CANDIDATE,
            origin_kind=SpecOriginKind.KNOWLEDGE_SUGGESTION,
            origin_ref_id=origin.suggestion_id,
        )
        rule = RuleDeclarationSpec(
            rule_id="rule_domain_mismatch",
            semantic_key="order.queue",
            rule_kind="all_conditions_match",
            subject_type_id=second.type_id,
            conditions=(
                RuleConditionSpec(
                    property_type_id=property_type.property_type_id,
                    operator="in",
                    allowed_values=("at_risk",),
                ),
            ),
            output_conclusion_key="priority_queue",
            positive_conclusion_value="enter",
            negative_conclusion_value="do_not_enter",
            description="Synthetic rule.",
            governance_status=SpecGovernanceStatus.CANDIDATE,
            origin_suggestion_id=origin.suggestion_id,
        )
        spec = replace(
            base,
            property_types=(property_type,),
            rule_declarations=(rule,),
        )

        report = validate_reference_closure(spec, pack)

        self.assertIn(
            "rule_property_domain_mismatch",
            {item.code for item in report.issues},
        )

    def test_multiple_elements_may_consume_one_suggestion(self):
        pack = golden_pack()
        base = golden_spec(pack)
        relation = next(
            item
            for item in base.relation_types
            if item.origin_kind is SpecOriginKind.KNOWLEDGE_SUGGESTION
        )
        second = replace(relation, relation_type_id=f"{relation.relation_type_id}_second")
        spec = replace(base, relation_types=base.relation_types + (second,))

        report = validate_reference_closure(spec, pack)

        self.assertTrue(report.is_closed)

    def test_element_and_issue_consumption_is_duplicate_not_unaccounted(self):
        pack = golden_pack()
        base = golden_spec(pack)
        relation = next(
            item
            for item in base.relation_types
            if item.origin_kind is SpecOriginKind.KNOWLEDGE_SUGGESTION
        )
        suggestion = next(
            item
            for item in all_suggestions(pack)
            if item.suggestion_id == relation.origin_ref_id
        )
        duplicate_issue = CompilationIssue(
            issue_id="compilation_issue_duplicate_disposition",
            code="manual_review",
            severity=CompilationIssueSeverity.REQUIRES_REVIEW,
            suggestion_id=suggestion.suggestion_id,
            payload_schema=suggestion.payload_schema,
            message="Duplicate disposition.",
        )
        spec = replace(
            base,
            compilation_issues=base.compilation_issues + (duplicate_issue,),
        )

        report = validate_reference_closure(spec, pack)
        suggestion_codes = {
            item.code
            for item in report.issues
            if item.referenced_id == suggestion.suggestion_id
        }

        self.assertIn("duplicate_suggestion_consumption", suggestion_codes)
        self.assertNotIn("unaccounted_suggestion", suggestion_codes)

    def test_unconsumed_applicable_suggestion_is_reported(self):
        pack = golden_pack()
        base = golden_spec(pack)
        relation = next(
            item
            for item in base.relation_types
            if item.origin_kind is SpecOriginKind.KNOWLEDGE_SUGGESTION
        )
        spec = replace(
            base,
            relation_types=tuple(item for item in base.relation_types if item != relation),
        )

        report = validate_reference_closure(spec, pack)

        self.assertIn(
            relation.origin_ref_id,
            {
                item.referenced_id
                for item in report.issues
                if item.code == "unaccounted_suggestion"
            },
        )

    def test_issue_order_is_stable_and_duplicate_failures_are_deduplicated(self):
        pack = golden_pack()
        base = golden_spec(pack)
        first_relation = replace(
            base.relation_types[0],
            domain_type_id="entity_missing",
        )
        second_relation = replace(
            first_relation,
            relation_type_id="relation_second",
        )
        spec = replace(
            base,
            relation_types=(second_relation, first_relation),
        )

        report = validate_reference_closure(spec, pack)

        issue_ids = tuple(item.issue_id for item in report.issues)
        self.assertEqual(issue_ids, tuple(sorted(issue_ids, key=str.casefold)))
        self.assertEqual(len(issue_ids), len(set(issue_ids)))


if __name__ == "__main__":
    unittest.main()

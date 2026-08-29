import json
import unittest
from pathlib import Path
from unittest.mock import patch

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.decision_pack import DecisionPack
from ontology_poc_generator.errors import SpecCompilationError
from ontology_poc_generator.identity import stable_compilation_issue_id
from ontology_poc_generator.knowledge import (
    KnowledgeOutcome,
    KnowledgeUnit,
    load_knowledge_unit,
)
from ontology_poc_generator.ontology_spec import (
    ClosureIssue,
    CompilationIssueSeverity,
    CompilationStatus,
    EvidenceScope,
    ReferenceClosureReport,
    SpecGovernanceStatus,
    SpecOriginKind,
    SpecStage,
    canonical_ontology_spec_json,
)
from ontology_poc_generator.spec_compiler import compile_ontology_spec
from tests.test_decision_pack import minimal_scenario


ROOT = Path(__file__).parents[1]
UNIT_PATH = ROOT / "knowledge/supply_chain/supplier_evidence_boundary_v1.json"
POLICY_BASELINE_PATH = (
    ROOT / "knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json"
)
POLICY_CANDIDATE_PATH = (
    ROOT / "tests/fixtures/knowledge/order_priority_policy_synthetic_candidate_v2.json"
)


def provided_pack() -> DecisionPack:
    return compile_decision_pack(minimal_scenario())


def golden_pack(**scenario_overrides: object) -> DecisionPack:
    return compile_decision_pack(
        minimal_scenario(**scenario_overrides),
        (load_knowledge_unit(UNIT_PATH),),
    )


def policy_pack(path: Path = POLICY_BASELINE_PATH) -> DecisionPack:
    return compile_decision_pack(
        minimal_scenario(),
        (load_knowledge_unit(path),),
    )


def unsupported_policy_pack() -> DecisionPack:
    data = json.loads(POLICY_BASELINE_PATH.read_text(encoding="utf-8"))
    data["suggestion_templates"][0]["payload"]["rule_kind"] = (
        "rolling_probability_v1"
    )
    unit = KnowledgeUnit.from_dict(data, unit_content_hash="b" * 64)
    return compile_decision_pack(minimal_scenario(), (unit,))


class SpecCompilerTest(unittest.TestCase):
    def test_synthetic_policy_compiles_stable_declarations_and_changed_hash(self):
        baseline = compile_ontology_spec(policy_pack())
        candidate = compile_ontology_spec(policy_pack(POLICY_CANDIDATE_PATH))

        self.assertTrue(baseline.closure_report.is_closed)
        self.assertTrue(candidate.closure_report.is_closed)
        self.assertIs(baseline.compilation_status, CompilationStatus.COMPLETE)
        self.assertIs(candidate.compilation_status, CompilationStatus.COMPLETE)
        self.assertEqual(len(baseline.spec.property_types), 2)
        self.assertEqual(len(candidate.spec.property_types), 2)
        self.assertEqual(len(baseline.spec.rule_declarations), 1)
        self.assertEqual(len(candidate.spec.rule_declarations), 1)
        self.assertEqual(baseline.spec.compilation_issues, ())
        self.assertEqual(candidate.spec.compilation_issues, ())

        baseline_properties = {
            item.semantic_key: item for item in baseline.spec.property_types
        }
        candidate_properties = {
            item.semantic_key: item for item in candidate.spec.property_types
        }
        self.assertEqual(
            set(baseline_properties),
            {"supplier_commitment_state", "qualified_alternative_state"},
        )
        self.assertEqual(
            {
                key: item.property_type_id
                for key, item in baseline_properties.items()
            },
            {
                key: item.property_type_id
                for key, item in candidate_properties.items()
            },
        )
        self.assertEqual(
            {item.value_type for item in baseline.spec.property_types},
            {"symbolic_state"},
        )

        baseline_rule = baseline.spec.rule_declarations[0]
        candidate_rule = candidate.spec.rule_declarations[0]
        self.assertEqual(baseline_rule.rule_id, candidate_rule.rule_id)
        self.assertIs(
            baseline_rule.governance_status,
            SpecGovernanceStatus.CANDIDATE,
        )

        def conditions_by_semantic_key(result):
            properties_by_id = {
                item.property_type_id: item for item in result.spec.property_types
            }
            return {
                properties_by_id[condition.property_type_id].semantic_key: (
                    condition.operator,
                    condition.allowed_values,
                )
                for condition in result.spec.rule_declarations[0].conditions
            }

        self.assertEqual(
            conditions_by_semantic_key(baseline),
            {
                "supplier_commitment_state": ("in", ("missed",)),
                "qualified_alternative_state": ("in", ("none",)),
            },
        )
        self.assertEqual(
            conditions_by_semantic_key(candidate),
            {
                "supplier_commitment_state": (
                    "in",
                    ("at_risk", "missed"),
                ),
                "qualified_alternative_state": ("in", ("none",)),
            },
        )
        self.assertNotEqual(
            baseline.spec_content_hash,
            candidate.spec_content_hash,
        )

    def test_unsupported_rule_kind_is_one_blocking_compiler_disposition(self):
        pack = unsupported_policy_pack()

        result = compile_ontology_spec(pack)

        self.assertTrue(result.closure_report.is_closed)
        self.assertIs(result.compilation_status, CompilationStatus.BLOCKED)
        self.assertEqual(result.spec.property_types, ())
        self.assertEqual(result.spec.rule_declarations, ())
        self.assertEqual(len(result.spec.compilation_issues), 1)
        issue = result.spec.compilation_issues[0]
        suggestion = pack.knowledge_outcomes[0].suggestions[0]
        self.assertEqual(issue.code, "unsupported_rule_kind")
        self.assertIs(issue.severity, CompilationIssueSeverity.BLOCKING)
        self.assertEqual(
            issue.issue_id,
            stable_compilation_issue_id(
                suggestion.suggestion_id,
                "unsupported_rule_kind",
                "decision_rule.v1",
            ),
        )

    def test_readiness_gap_stays_review_only_alongside_compiled_rule(self):
        pack = compile_decision_pack(
            minimal_scenario(),
            (
                load_knowledge_unit(UNIT_PATH),
                load_knowledge_unit(POLICY_BASELINE_PATH),
            ),
        )

        result = compile_ontology_spec(pack)

        readiness_issue = next(
            issue
            for issue in result.spec.compilation_issues
            if issue.code == "readiness_gap_blocks_rule_compilation"
        )
        self.assertIs(
            readiness_issue.severity,
            CompilationIssueSeverity.REQUIRES_REVIEW,
        )
        self.assertTrue(result.closure_report.is_closed)
        self.assertIs(result.compilation_status, CompilationStatus.COMPLETE)
        self.assertEqual(len(result.spec.property_types), 2)
        self.assertEqual(len(result.spec.rule_declarations), 1)

    def test_provided_only_pack_compiles_to_closed_complete_result(self):
        result = compile_ontology_spec(provided_pack())

        self.assertTrue(result.closure_report.is_closed)
        self.assertGreater(result.closure_report.checked_reference_count, 0)
        self.assertIs(result.compilation_status, CompilationStatus.COMPLETE)
        self.assertEqual(len(result.spec.entity_types), 3)
        self.assertEqual(len(result.spec.relation_types), 1)
        self.assertEqual(result.spec.property_types, ())
        self.assertEqual(result.spec.rule_declarations, ())
        self.assertEqual(result.spec.compilation_issues, ())

    def test_golden_pack_merges_provided_and_knowledge_outputs(self):
        pack = golden_pack()

        result = compile_ontology_spec(pack)

        self.assertTrue(result.closure_report.is_closed)
        self.assertIs(result.compilation_status, CompilationStatus.COMPLETE)
        self.assertEqual(len(result.spec.relation_types), 3)
        self.assertEqual(
            len(
                [
                    relation
                    for relation in result.spec.relation_types
                    if relation.origin_kind
                    is SpecOriginKind.KNOWLEDGE_SUGGESTION
                ]
            ),
            2,
        )
        self.assertEqual(len(result.spec.compilation_issues), 5)
        self.assertEqual(result.spec.property_types, ())
        self.assertEqual(result.spec.rule_declarations, ())

    def test_every_applicable_suggestion_is_consumed_exactly_once(self):
        pack = golden_pack()

        result = compile_ontology_spec(pack)

        suggestion_ids = {
            suggestion.suggestion_id
            for outcome in pack.knowledge_outcomes
            for suggestion in outcome.suggestions
        }
        consumed_ids = [
            item.origin_ref_id
            for item in result.spec.relation_types
            if item.origin_kind is SpecOriginKind.KNOWLEDGE_SUGGESTION
        ] + [item.suggestion_id for item in result.spec.compilation_issues]
        self.assertEqual(set(consumed_ids), suggestion_ids)
        self.assertEqual(len(consumed_ids), len(suggestion_ids))

    def test_canonical_bytes_and_hash_are_repeatable_and_order_stable(self):
        pack = golden_pack()
        outcome = pack.knowledge_outcomes[0]
        reordered_outcome = KnowledgeOutcome(
            unit_id=outcome.unit_id,
            unit_version=outcome.unit_version,
            unit_content_hash=outcome.unit_content_hash,
            match_status=outcome.match_status,
            reason_code=outcome.reason_code,
            input_binding_ids=tuple(reversed(outcome.input_binding_ids)),
            suggestions=tuple(reversed(outcome.suggestions)),
        )
        reordered_pack = DecisionPack(
            schema=pack.schema,
            scenario=pack.scenario,
            input_bindings=tuple(reversed(pack.input_bindings)),
            source_refs=tuple(reversed(pack.source_refs)),
            knowledge_outcomes=(reordered_outcome,),
        )

        first = compile_ontology_spec(pack)
        repeated = compile_ontology_spec(pack)
        reordered = compile_ontology_spec(reordered_pack)

        self.assertEqual(
            canonical_ontology_spec_json(first.spec),
            canonical_ontology_spec_json(repeated.spec),
        )
        self.assertEqual(first.spec_content_hash, repeated.spec_content_hash)
        self.assertEqual(
            canonical_ontology_spec_json(first.spec),
            canonical_ontology_spec_json(reordered.spec),
        )
        self.assertEqual(first.spec_content_hash, reordered.spec_content_hash)

    def test_label_change_preserves_ids_but_changes_content_hash(self):
        first = compile_ontology_spec(golden_pack())
        renamed = compile_ontology_spec(
            golden_pack(
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
        )

        self.assertEqual(
            {item.type_id for item in first.spec.entity_types},
            {item.type_id for item in renamed.spec.entity_types},
        )
        self.assertEqual(
            {item.relation_type_id for item in first.spec.relation_types},
            {item.relation_type_id for item in renamed.spec.relation_types},
        )
        self.assertNotEqual(first.spec_content_hash, renamed.spec_content_hash)

    def test_fatal_compilation_error_code_passes_through_unchanged(self):
        for code in (
            "duplicate_relation_type_identity",
            "missing_relation_role_binding",
        ):
            with self.subTest(code=code), patch(
                "ontology_poc_generator.spec_compiler.compile_knowledge_profiles",
                side_effect=SpecCompilationError(code, "fatal"),
            ):
                with self.assertRaises(SpecCompilationError) as caught:
                    compile_ontology_spec(golden_pack())
                self.assertEqual(caught.exception.code, code)

    def test_open_reference_closure_cannot_form_a_compilation_result(self):
        open_report = ReferenceClosureReport(
            checked_reference_count=1,
            issues=(
                ClosureIssue(
                    issue_id="closure_issue_open",
                    code="dangling_relation_domain",
                    owner_id="relation_open",
                    field="domain_type_id",
                    referenced_id="entity_missing",
                ),
            ),
        )

        with patch(
            "ontology_poc_generator.spec_compiler.validate_reference_closure",
            return_value=open_report,
        ):
            with self.assertRaises(SpecCompilationError) as caught:
                compile_ontology_spec(provided_pack())

        self.assertEqual(caught.exception.code, "compiled_spec_not_reference_closed")

    def test_default_envelope_remains_synthetic_draft_candidate(self):
        spec = compile_ontology_spec(golden_pack()).spec

        self.assertIs(spec.stage, SpecStage.DRAFT)
        self.assertIs(spec.evidence_scope, EvidenceScope.SYNTHETIC_DEMO)
        self.assertIs(spec.governance_status, SpecGovernanceStatus.CANDIDATE)


if __name__ == "__main__":
    unittest.main()

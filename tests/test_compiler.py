import dataclasses
import hashlib
import json
import unittest
from pathlib import Path

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.decision_pack import DecisionPack, decision_pack_content_hash
from ontology_poc_generator.errors import KnowledgeValidationError
from ontology_poc_generator.generator import generate_proposal
from ontology_poc_generator.knowledge import KnowledgeUnit, MatchStatus, load_knowledge_unit
from ontology_poc_generator.models import ScenarioParameters
from ontology_poc_generator.renderers import render_json, render_markdown
from tests.test_decision_pack import minimal_scenario


ROOT = Path(__file__).parents[1]
UNIT_PATH = ROOT / "knowledge/supply_chain/supplier_evidence_boundary_v1.json"


class CompilerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.unit = load_knowledge_unit(UNIT_PATH)

    def _other_unit(self, *, conflicting_source=False):
        other_id = "other.supplier_evidence"
        other_hash = "1" * 64
        sources = self.unit.source_refs
        if conflicting_source:
            sources = (
                dataclasses.replace(sources[0], caveat="Conflicting caveat."),
                *sources[1:],
            )
        return KnowledgeUnit(
            unit_id=other_id,
            unit_version="1.0.0",
            decision_key=self.unit.decision_key,
            unit_content_hash=other_hash,
            source_refs=sources,
            suggestion_templates=tuple(
                dataclasses.replace(
                    template,
                    unit_id=other_id,
                    unit_content_hash=other_hash,
                )
                for template in self.unit.suggestion_templates
            ),
            applicability=self.unit.applicability,
        )

    def test_applicable_pack_has_external_candidates_and_exact_provenance_closure(self):
        params = minimal_scenario()
        pack = compile_decision_pack(params, (self.unit,))

        self.assertEqual(pack.schema, "decision_pack.v1")
        self.assertEqual(pack.knowledge_outcomes[0].match_status, MatchStatus.APPLICABLE)
        suggestions = pack.knowledge_outcomes[0].suggestions
        self.assertTrue(suggestions)
        self.assertTrue(all(item.governance_status == "candidate" for item in suggestions))
        self.assertTrue(all(item.unit_content_hash == self.unit.unit_content_hash for item in suggestions))
        scenario_text = json.dumps(dataclasses.asdict(params), ensure_ascii=False)
        self.assertTrue(any(item.semantic_key not in scenario_text for item in suggestions))
        cited = {source_id for item in suggestions for source_id in item.source_ref_ids}
        self.assertEqual({source.source_ref_id for source in pack.source_refs}, cited)
        self.assertTrue(
            all(
                set(item.input_binding_ids).issubset({binding.binding_id for binding in pack.input_bindings})
                for item in suggestions
            )
        )

    def test_mismatch_and_insufficient_outcomes_have_no_suggestions_or_sources(self):
        mismatch = minimal_scenario(decision_key="different_decision")
        insufficient = minimal_scenario(declared_bridges=[])

        for params, expected in (
            (mismatch, MatchStatus.NOT_APPLICABLE),
            (insufficient, MatchStatus.INSUFFICIENT_INFORMATION),
        ):
            with self.subTest(expected=expected):
                pack = compile_decision_pack(params, (self.unit,))
                self.assertEqual(pack.knowledge_outcomes[0].match_status, expected)
                self.assertEqual(pack.knowledge_outcomes[0].suggestions, ())
                self.assertEqual(pack.source_refs, ())

    def test_compilation_filters_ready_gap_without_changing_match_status(self):
        ready = minimal_scenario(
            readiness_declarations=[
                {"requirement_key": "queue_entry_evidence_policy", "status": "ready"}
            ]
        )
        pending = minimal_scenario(
            readiness_declarations=[
                {"requirement_key": "queue_entry_evidence_policy", "status": "to_confirm"}
            ]
        )

        ready_pack = compile_decision_pack(ready, (self.unit,))
        pending_pack = compile_decision_pack(pending, (self.unit,))

        self.assertEqual(ready_pack.knowledge_outcomes[0].match_status, MatchStatus.APPLICABLE)
        self.assertNotIn("readiness_gap", {item.contribution_type for item in ready_pack.knowledge_outcomes[0].suggestions})
        self.assertIn("readiness_gap", {item.contribution_type for item in pending_pack.knowledge_outcomes[0].suggestions})

    def test_reordering_collections_and_units_keeps_ids_and_hash(self):
        relations = [
            {"source": "订单", "predicate": "需要", "target": "物料"},
            {"source": "供应商", "predicate": "提供", "target": "物料"},
        ]
        first = minimal_scenario(relations=relations)
        second = minimal_scenario(
            objects=["供应商", "订单", "物料"],
            relations=list(reversed(relations)),
            object_role_bindings=list(reversed([
                {"role_key": "customer_order", "semantic_key": "order.primary", "object_label": "订单"},
                {"role_key": "material", "semantic_key": "material.required", "object_label": "物料"},
                {"role_key": "supplier", "semantic_key": "supplier.candidate", "object_label": "供应商"},
            ])),
        )

        other = self._other_unit()
        first_pack = compile_decision_pack(first, (self.unit, other))
        second_pack = compile_decision_pack(second, (other, self.unit))

        self.assertEqual(
            tuple(item.binding_id for item in first_pack.input_bindings),
            tuple(item.binding_id for item in second_pack.input_bindings),
        )
        self.assertEqual(
            tuple(
                item.suggestion_id
                for outcome in first_pack.knowledge_outcomes
                for item in outcome.suggestions
            ),
            tuple(
                item.suggestion_id
                for outcome in second_pack.knowledge_outcomes
                for item in outcome.suggestions
            ),
        )
        self.assertEqual(decision_pack_content_hash(first_pack), decision_pack_content_hash(second_pack))

    def test_label_rename_keeps_ids_but_changes_pack_hash(self):
        first = minimal_scenario()
        renamed = minimal_scenario(
            objects=["客户单", "物资", "供方"],
            object_role_bindings=[
                {"role_key": "customer_order", "semantic_key": "order.primary", "object_label": "客户单"},
                {"role_key": "material", "semantic_key": "material.required", "object_label": "物资"},
                {"role_key": "supplier", "semantic_key": "supplier.candidate", "object_label": "供方"},
            ],
        )

        first_pack = compile_decision_pack(first, (self.unit,))
        renamed_pack = compile_decision_pack(renamed, (self.unit,))

        self.assertEqual(
            tuple(item.binding_id for item in first_pack.input_bindings),
            tuple(item.binding_id for item in renamed_pack.input_bindings),
        )
        self.assertEqual(
            tuple(item.suggestion_id for item in first_pack.knowledge_outcomes[0].suggestions),
            tuple(item.suggestion_id for item in renamed_pack.knowledge_outcomes[0].suggestions),
        )
        self.assertNotEqual(decision_pack_content_hash(first_pack), decision_pack_content_hash(renamed_pack))

    def test_duplicate_unit_id_is_rejected(self):
        with self.assertRaisesRegex(KnowledgeValidationError, "duplicate knowledge unit_id"):
            compile_decision_pack(minimal_scenario(), (self.unit, self.unit))

    def test_same_source_id_with_different_content_is_rejected(self):
        with self.assertRaisesRegex(KnowledgeValidationError, "conflicting content"):
            compile_decision_pack(
                minimal_scenario(), (self.unit, self._other_unit(conflicting_source=True))
            )

    def test_pack_rejects_missing_cited_source_after_manual_tampering(self):
        valid = compile_decision_pack(minimal_scenario(), (self.unit,))

        with self.assertRaisesRegex(KnowledgeValidationError, "source outside pack"):
            DecisionPack(
                valid.schema,
                valid.scenario,
                valid.input_bindings,
                valid.source_refs[:-1],
                valid.knowledge_outcomes,
            )

    def test_caller_list_mutation_cannot_change_existing_pack_hash(self):
        objects = ["订单", "物料", "供应商"]
        role = {
            "role_key": "customer_order",
            "semantic_key": "order.primary",
            "object_label": "订单",
        }
        params = minimal_scenario(
            objects=objects,
            object_role_bindings=[
                role,
                {"role_key": "material", "semantic_key": "material.required", "object_label": "物料"},
                {"role_key": "supplier", "semantic_key": "supplier.candidate", "object_label": "供应商"},
            ],
        )
        pack = compile_decision_pack(params, (self.unit,))
        before = decision_pack_content_hash(pack)

        objects[0] = "已修改订单"
        role["semantic_key"] = "changed"

        self.assertEqual(decision_pack_content_hash(pack), before)

    def test_candidates_do_not_contain_business_results_or_lifecycle_fields(self):
        pack = compile_decision_pack(minimal_scenario(), (self.unit,))
        forbidden_payload_keys = {
            "score", "queue_membership", "action", "rule_result", "review",
            "version", "base", "publication", "facts", "receipt",
        }

        for suggestion in pack.knowledge_outcomes[0].suggestions:
            self.assertTrue(forbidden_payload_keys.isdisjoint(dict(suggestion.payload)))
            self.assertNotIn(suggestion.contribution_type, {"action", "rule_result"})

    def test_proposal_projects_pack_without_flattening_suggestions(self):
        proposal = generate_proposal(minimal_scenario(), (self.unit,))

        self.assertEqual(len(proposal.knowledge_outcomes), 1)
        self.assertTrue(proposal.knowledge_outcomes[0].suggestions)
        self.assertEqual(proposal.knowledge_source_refs, compile_decision_pack(minimal_scenario(), (self.unit,)).source_refs)
        self.assertFalse(hasattr(proposal, "knowledge_suggestions"))

    def test_no_unit_projection_preserves_exact_loop0_json_and_markdown(self):
        params = ScenarioParameters.from_dict({
            "industry": "乳制品研发",
            "scene_name": "候选实验方向设计",
            "business_decision": "选择下一轮候选实验方向",
            "decision_owner": "研发项目负责人",
            "trigger": "完成需求澄清后",
            "objects": ["研发目标", "候选配方", "实验"],
            "acceptance_questions": ["能否解释候选方向的依据？"],
            "customer_data_available": False,
        })
        proposal = generate_proposal(params)
        rendered_json = render_json(proposal)
        rendered_markdown = render_markdown(proposal)

        self.assertEqual(len(json.loads(rendered_json)), 20)
        self.assertEqual(hashlib.sha256(rendered_json.encode()).hexdigest(), "2607c8161e326eee2628d566fac45c76db45c7b8f4e3e9ec4d2c9bbde97c5e6e")
        self.assertEqual(hashlib.sha256(rendered_markdown.encode()).hexdigest(), "73eff9206ebf3efce783a6485f27a57c12f632c3c7821bd454d7ba52a1edb680")
        self.assertFalse(rendered_json.endswith("\n"))
        self.assertTrue(rendered_markdown.endswith("\n"))


if __name__ == "__main__":
    unittest.main()

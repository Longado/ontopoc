import dataclasses
import importlib
import json
import unittest
from pathlib import Path

from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.decision_pack import decision_pack_content_hash
from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.ontology_spec import SpecCompilationResult
from ontology_poc_generator.spec_compiler import compile_ontology_spec
from ontology_poc_generator.validation_receipt import (
    DecisionResult,
    EvaluationStatus,
)
from tests.test_decision_pack import minimal_scenario


ROOT = Path(__file__).parents[1]
BASELINE_POLICY = (
    ROOT / "knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json"
)
CANDIDATE_POLICY = (
    ROOT / "tests/fixtures/knowledge/order_priority_policy_synthetic_candidate_v2.json"
)
CASES_PATH = ROOT / "tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json"


def runtime_module():
    try:
        return importlib.import_module("ontology_poc_generator.rule_runtime")
    except ModuleNotFoundError:
        raise AssertionError("rule_runtime module is not implemented") from None


def compiled_policy(path: Path):
    pack = compile_decision_pack(
        minimal_scenario(),
        (load_knowledge_unit(path),),
    )
    return pack, compile_ontology_spec(pack)


def synthetic_facts(compilation, case):
    runtime = runtime_module()
    properties = {
        item.semantic_key: item.property_type_id
        for item in compilation.spec.property_types
    }
    values = []
    for semantic_key, raw in case["inputs"].items():
        values.append(
            runtime.SyntheticFact(
                fact_ref=f"{case['subject_id']}:{semantic_key}",
                property_type_id=properties[semantic_key],
                availability=runtime.FactAvailability(raw["availability"]),
                value=raw.get("value"),
                evidence_refs=(f"evidence:{case['subject_id']}:{semantic_key}",),
            )
        )
    return runtime.SyntheticFactSet(
        schema="synthetic_fact_set.v1",
        evidence_scope="synthetic_demo",
        subject_id=case["subject_id"],
        facts=tuple(values),
    )


class RuleRuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"]

    def test_four_synthetic_cases_produce_bound_baseline_and_candidate_receipts(self):
        runtime = runtime_module()
        baseline_pack, baseline = compiled_policy(BASELINE_POLICY)
        candidate_pack, candidate = compiled_policy(CANDIDATE_POLICY)

        self.assertEqual(
            baseline.spec.rule_declarations[0].rule_id,
            candidate.spec.rule_declarations[0].rule_id,
        )

        for case in self.cases:
            for label, pack, compilation in (
                ("baseline", baseline_pack, baseline),
                ("candidate", candidate_pack, candidate),
            ):
                with self.subTest(subject=case["subject_id"], version=label):
                    facts = synthetic_facts(compilation, case)
                    receipt = runtime.evaluate_synthetic_rule(
                        pack,
                        compilation,
                        facts,
                        compilation.spec.rule_declarations[0].rule_id,
                    )
                    expected = case["expected"][label]

                    self.assertIs(
                        receipt.evaluation_status,
                        EvaluationStatus(expected["evaluation_status"]),
                    )
                    self.assertIs(
                        receipt.decision_result,
                        DecisionResult(expected["conclusion_value"]),
                    )
                    self.assertEqual(
                        receipt.decision_pack_content_hash,
                        decision_pack_content_hash(pack),
                    )
                    self.assertEqual(
                        receipt.ontology_spec_content_hash,
                        compilation.spec_content_hash,
                    )
                    self.assertEqual(
                        receipt.facts_content_hash,
                        runtime.synthetic_fact_set_content_hash(facts),
                    )
                    self.assertEqual(
                        receipt.rule_id,
                        compilation.spec.rule_declarations[0].rule_id,
                    )
                    self.assertEqual(
                        set(receipt.fact_refs),
                        {item.fact_ref for item in facts.facts},
                    )
                    self.assertIn(
                        "synthetic_order_priority_policy_cases_v1",
                        receipt.evidence_refs,
                    )
                    self.assertFalse(receipt.draft_created)
                    self.assertFalse(receipt.published)
                    self.assertFalse(receipt.actions_executed)
                    self.assertFalse(receipt.external_write)

    def test_candidate_changes_only_the_at_risk_case_from_fail_to_pass(self):
        runtime = runtime_module()
        baseline_pack, baseline = compiled_policy(BASELINE_POLICY)
        candidate_pack, candidate = compiled_policy(CANDIDATE_POLICY)
        case = self.cases[1]

        baseline_receipt = runtime.evaluate_synthetic_rule(
            baseline_pack,
            baseline,
            synthetic_facts(baseline, case),
            baseline.spec.rule_declarations[0].rule_id,
        )
        candidate_receipt = runtime.evaluate_synthetic_rule(
            candidate_pack,
            candidate,
            synthetic_facts(candidate, case),
            candidate.spec.rule_declarations[0].rule_id,
        )

        self.assertIs(baseline_receipt.evaluation_status, EvaluationStatus.FAIL)
        self.assertIs(candidate_receipt.evaluation_status, EvaluationStatus.PASS)
        self.assertNotEqual(
            baseline_receipt.ontology_spec_content_hash,
            candidate_receipt.ontology_spec_content_hash,
        )

    def test_unknown_rule_kind_returns_unsupported_without_execution(self):
        runtime = runtime_module()
        pack, compilation = compiled_policy(BASELINE_POLICY)
        rule = dataclasses.replace(
            compilation.spec.rule_declarations[0],
            rule_kind="rolling_probability_v1",
        )
        unsupported = SpecCompilationResult(
            spec=dataclasses.replace(
                compilation.spec,
                rule_declarations=(rule,),
            ),
            closure_report=compilation.closure_report,
        )

        receipt = runtime.evaluate_synthetic_rule(
            pack,
            unsupported,
            synthetic_facts(unsupported, self.cases[0]),
            rule.rule_id,
        )

        self.assertIs(receipt.evaluation_status, EvaluationStatus.UNSUPPORTED)
        self.assertIs(receipt.decision_result, DecisionResult.UNSUPPORTED)
        self.assertFalse(receipt.actions_executed)
        self.assertFalse(receipt.external_write)

    def test_fact_contract_rejects_non_synthetic_or_incoherent_values(self):
        runtime = runtime_module()
        fact = runtime.SyntheticFact(
            fact_ref="fact-1",
            property_type_id="property-1",
            availability=runtime.FactAvailability.AVAILABLE,
            value="missed",
            evidence_refs=("evidence-1",),
        )

        for changes, message in (
            ({"availability": runtime.FactAvailability.UNAVAILABLE}, "value"),
            ({"value": None}, "value"),
        ):
            with self.subTest(changes=changes), self.assertRaisesRegex(
                runtime.RuleEvaluationError,
                message,
            ):
                dataclasses.replace(fact, **changes)

        with self.assertRaisesRegex(runtime.RuleEvaluationError, "evidence_scope"):
            runtime.SyntheticFactSet(
                schema="synthetic_fact_set.v1",
                evidence_scope="customer_data",
                subject_id="order-1",
                facts=(fact,),
            )

        with self.assertRaisesRegex(runtime.RuleEvaluationError, "evidence_refs"):
            dataclasses.replace(
                fact,
                evidence_refs=("Evidence-1", "evidence-1"),
            )

    def test_missing_required_fact_returns_not_evaluable_with_stable_reference(self):
        runtime = runtime_module()
        pack, compilation = compiled_policy(BASELINE_POLICY)
        complete_facts = synthetic_facts(compilation, self.cases[0])
        incomplete_facts = dataclasses.replace(
            complete_facts,
            facts=(complete_facts.facts[0],),
        )
        rule = compilation.spec.rule_declarations[0]
        missing_property_id = next(
            condition.property_type_id
            for condition in rule.conditions
            if condition.property_type_id != incomplete_facts.facts[0].property_type_id
        )

        receipt = runtime.evaluate_synthetic_rule(
            pack,
            compilation,
            incomplete_facts,
            rule.rule_id,
        )

        self.assertIs(
            receipt.evaluation_status,
            EvaluationStatus.NOT_EVALUABLE,
        )
        self.assertIs(
            receipt.decision_result,
            DecisionResult.INFORMATION_INSUFFICIENT,
        )
        self.assertIn(
            f"missing:{incomplete_facts.subject_id}:{missing_property_id}",
            receipt.fact_refs,
        )

    def test_pack_and_spec_hash_mismatch_is_rejected(self):
        runtime = runtime_module()
        baseline_pack, _ = compiled_policy(BASELINE_POLICY)
        _, candidate = compiled_policy(CANDIDATE_POLICY)

        with self.assertRaisesRegex(runtime.RuleEvaluationError, "pack_content_hash"):
            runtime.evaluate_synthetic_rule(
                baseline_pack,
                candidate,
                synthetic_facts(candidate, self.cases[0]),
                candidate.spec.rule_declarations[0].rule_id,
            )


if __name__ == "__main__":
    unittest.main()

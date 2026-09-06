import dataclasses
import importlib
import unittest

from ontology_poc_generator.decision_pack import decision_pack_content_hash
from ontology_poc_generator.errors import OntologySpecValidationError
from ontology_poc_generator.ontology_spec import ontology_spec_content_hash
from ontology_poc_generator.spec_compiler import compile_ontology_spec
from tests.test_spec_compiler import policy_pack


def implementation_map_module():
    try:
        return importlib.import_module("ontology_poc_generator.implementation_map")
    except ModuleNotFoundError:
        raise AssertionError("implementation_map module is not implemented") from None


class ImplementationMapTest(unittest.TestCase):
    def test_projects_compiled_elements_to_evidence_and_real_consumers(self):
        module = implementation_map_module()
        pack = policy_pack()
        compilation = compile_ontology_spec(pack)

        result = module.build_implementation_map(pack, compilation)

        self.assertEqual(result["schema"], "implementation_map.v1")
        self.assertEqual(result["decision_key"], pack.scenario.decision_key)
        self.assertEqual(
            result["decision_pack_content_hash"], decision_pack_content_hash(pack)
        )
        self.assertEqual(
            result["ontology_spec_content_hash"],
            ontology_spec_content_hash(compilation.spec),
        )
        self.assertIs(result["editable"], False)

        entries = result["entries"]
        self.assertEqual(
            entries,
            sorted(
                entries,
                key=lambda item: (
                    item["element_kind"].casefold(),
                    item["element_id"].casefold(),
                ),
            ),
        )
        self.assertEqual(
            {item["element_kind"] for item in entries},
            {"entity_type", "relation_type", "property_type", "rule_declaration"},
        )

        rule = next(
            item for item in entries if item["element_kind"] == "rule_declaration"
        )
        self.assertEqual(rule["execution_state"], "runtime_executable")
        self.assertEqual(
            rule["source_ref_ids"],
            ["synthetic_order_priority_policy_cases_v1"],
        )
        self.assertIn(
            "ontology_poc_generator.rule_runtime:evaluate_synthetic_rule",
            rule["implementation_refs"],
        )
        self.assertIn(
            "ontology_poc_generator.validation_receipt:ValidationReceipt",
            rule["implementation_refs"],
        )

        properties = [
            item for item in entries if item["element_kind"] == "property_type"
        ]
        self.assertTrue(properties)
        self.assertTrue(
            all(item["execution_state"] == "runtime_input" for item in properties)
        )
        self.assertTrue(
            all(
                item["source_ref_ids"]
                == ["synthetic_order_priority_policy_cases_v1"]
                for item in properties
            )
        )

        declarations = [
            item
            for item in entries
            if item["element_kind"] in {"entity_type", "relation_type"}
        ]
        self.assertTrue(declarations)
        self.assertTrue(
            all(item["execution_state"] == "declared_only" for item in declarations)
        )
        self.assertTrue(
            all(
                item["implementation_refs"]
                == [
                    "ontology_poc_generator.validation:validate_reference_closure"
                ]
                for item in declarations
            )
        )

    def test_rejects_a_spec_compiled_from_a_different_decision_pack(self):
        module = implementation_map_module()
        pack = policy_pack()
        compilation = compile_ontology_spec(pack)
        mismatched = dataclasses.replace(
            compilation,
            spec=dataclasses.replace(
                compilation.spec,
                pack_content_hash="f" * 64,
            ),
        )

        with self.assertRaisesRegex(
            OntologySpecValidationError,
            "pack_content_hash does not match DecisionPack",
        ):
            module.build_implementation_map(pack, mismatched)


if __name__ == "__main__":
    unittest.main()

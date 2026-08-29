import unittest

from ontology_poc_generator.identity import (
    stable_binding_id,
    stable_compilation_issue_id,
    stable_entity_type_id,
    stable_property_type_id,
    stable_relation_type_id,
    stable_rule_id,
)


class StableIdentityTest(unittest.TestCase):
    def test_binding_id_ignores_display_label_and_object_order(self):
        original = stable_binding_id(
            "order_priority_intervention", "customer_order", "order.primary"
        )
        renamed = stable_binding_id(
            "order_priority_intervention", "customer_order", "order.primary"
        )

        self.assertEqual(original, renamed)

    def test_binding_id_changes_when_semantic_key_changes(self):
        original = stable_binding_id(
            "order_priority_intervention", "customer_order", "order.primary"
        )
        changed = stable_binding_id(
            "order_priority_intervention", "customer_order", "order.secondary"
        )

        self.assertNotEqual(original, changed)

    def test_spec_ids_use_stable_semantic_inputs_and_expected_prefixes(self):
        entity_id = stable_entity_type_id(
            "order_priority_intervention", "supplier", "supplier.candidate"
        )
        relation_id = stable_relation_type_id(
            "supplier_qualified_to_supply_material",
            entity_id,
            "QUALIFIED_TO_SUPPLY",
            "type_material",
        )
        property_id = stable_property_type_id(
            "supplier.commitment_state", entity_id
        )
        rule_id = stable_rule_id(
            "order_priority.queue_entry",
            "categorical_all_of_v1",
            "type_order",
            "priority_intervention_queue",
        )
        issue_id = stable_compilation_issue_id(
            "suggestion_rule",
            "unsupported_payload_schema",
            "decision_rule.v2",
        )

        self.assertTrue(entity_id.startswith("entity_type_"))
        self.assertTrue(relation_id.startswith("relation_type_"))
        self.assertTrue(property_id.startswith("property_type_"))
        self.assertTrue(rule_id.startswith("rule_"))
        self.assertTrue(issue_id.startswith("compilation_issue_"))
        self.assertEqual(
            entity_id,
            stable_entity_type_id(
                "order_priority_intervention", "supplier", "supplier.candidate"
            ),
        )

    def test_spec_ids_change_when_identity_bearing_inputs_change(self):
        self.assertNotEqual(
            stable_entity_type_id("decision", "supplier", "supplier.primary"),
            stable_entity_type_id("decision", "supplier", "supplier.secondary"),
        )
        self.assertNotEqual(
            stable_relation_type_id("bridge", "type_a", "REQUIRES", "type_b"),
            stable_relation_type_id("bridge", "type_a", "USES", "type_b"),
        )
        self.assertNotEqual(
            stable_property_type_id("order.state", "type_order"),
            stable_property_type_id("order.state", "type_supplier"),
        )
        self.assertNotEqual(
            stable_rule_id("rule", "all", "type_order", "queue"),
            stable_rule_id("rule", "any", "type_order", "queue"),
        )
        self.assertNotEqual(
            stable_compilation_issue_id("suggestion", "unsupported", "rule.v1"),
            stable_compilation_issue_id("suggestion", "invalid", "rule.v1"),
        )


if __name__ == "__main__":
    unittest.main()

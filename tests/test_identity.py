import unittest

from ontology_poc_generator.identity import stable_binding_id


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


if __name__ == "__main__":
    unittest.main()

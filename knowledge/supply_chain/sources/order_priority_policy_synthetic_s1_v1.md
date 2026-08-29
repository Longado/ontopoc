# Synthetic order-priority policy S-1 — source snapshot

This source is a synthetic test policy. It is not a customer fact, not an industry standard, and not a production threshold. It defines no Action or score.

- path: `tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json`
- revision: `ff327cbe9697e9651cd01ed2490da0ac97ed3d90`
- snapshot_sha256: `77a70331b2e6bcf5c7e6cae12a49717c77a176dc2194af5f4e44b4d3b0d1a487`
- source_kind: `synthetic_example`
- evidence_scope: `synthetic_demo`
- supported_suggestion_id: `rule.order_priority.synthetic_s1`

The baseline fixture proposes queue membership when the supplier commitment is `missed` and no qualified alternative is available. The candidate fixture adds `at_risk` to the first controlled condition. Both versions remain candidate test inputs and are not evaluated or published in this loop.

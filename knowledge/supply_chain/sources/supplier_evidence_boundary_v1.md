# Supplier evidence boundary v1 — source snapshots

This note records the fixed evidence snapshots used by the candidate knowledge unit. The loader reads only the adjacent JSON package; it does not read or import `nano-ontoprompt` at runtime. Hashes cover the complete named files, while fragments are human-readable locators.

## EIP quality vocabulary v11

- repository: `nano-ontoprompt`
- path: `backend/app/eip_extensions/quality/vocabulary.yaml`
- fragment: `lines 19-32`
- revision: `version: 11`
- snapshot_sha256: `1e8b7bf0a128f716d55ab438a0830959dadd15cebcc91e576eee67e2ffd71425`
- supported_suggestion_ids: `relation.qualified_to_supply`, `relation.has_supplied`, `constraint.history_not_qualification`, `data_requirement.material_qualification_snapshot`
- caveat: First-party implemented artifact, not a customer fact or industry standard. It supports a material-level qualification relation, qualification evidence, and an ASL or supplier-master source; it does not define the candidate field coverage or prove customer data completeness. The candidate output uses the explicit predicate `QUALIFIED_TO_SUPPLY` instead of the historical `SUPPLIES` name.

## EIP synthetic qualification/history cases

- repository: `nano-ontoprompt`
- path: `backend/tests/test_eip_supply_chain_risk.py`
- fragment: `qualification/history cases`
- revision: `qualification/history cases`
- snapshot_sha256: `a937a6b085733766b09ff5f40468ef9e9b1182c946d1cff9a201947111d27ed8`
- supported_suggestion_ids: `constraint.history_not_qualification`, `acceptance.qualification_absence_is_insufficient`
- caveat: Synthetic test behavior, not a production outcome. It supports the boundary that purchase history is not qualification and missing qualification data is not zero qualified supply.

## Loop 1 product methodology snapshot

- repository: `ontology-poc-generator`
- path: `docs/superpowers/plans/2026-08-29-loop1-sourced-supply-chain-knowledge.md`
- fragment: `lines 149-165`
- revision: `310c4d07bcc975fa955dea7a29f5dc7cc12172e4`
- snapshot_sha256: `639616ae2ede7eece52d765992ed41b41b2fae1b36fbc0af1968123d16c95ba3`
- supported_suggestion_ids: `data_requirement.material_qualification_snapshot`, `data_requirement.order_material_identity_mapping`, `readiness.queue_entry_policy_pending`
- caveat: A product methodology assumption, not a customer or industry fact. It supplies the candidate field coverage for qualification status, validity, scope, and snapshot completeness, plus the order-material bridge and queue-policy readiness requirements; none are customer-confirmed or evaluated.

from __future__ import annotations

import hashlib
import json


def _stable_id(prefix: str, parts: tuple[str, ...]) -> str:
    canonical = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest}"


def stable_binding_id(
    decision_key: str,
    role_key: str,
    semantic_key: str,
) -> str:
    """Return an identity that is independent of labels, position, and time."""
    return _stable_id("binding", (decision_key, role_key, semantic_key))


def stable_suggestion_id(
    unit_id: str,
    unit_version: str,
    semantic_key: str,
    input_binding_ids: tuple[str, ...],
) -> str:
    """Return an instantiated suggestion identity from stable semantic inputs."""
    return _stable_id(
        "suggestion",
        (unit_id, unit_version, semantic_key, *input_binding_ids),
    )


def stable_entity_type_id(
    decision_key: str,
    role_key: str,
    semantic_key: str,
) -> str:
    return _stable_id("entity_type", (decision_key, role_key, semantic_key))


def stable_relation_type_id(
    semantic_key: str,
    domain_type_id: str,
    predicate: str,
    range_type_id: str,
) -> str:
    return _stable_id(
        "relation_type",
        (semantic_key, domain_type_id, predicate, range_type_id),
    )


def stable_property_type_id(
    semantic_key: str,
    domain_type_id: str,
) -> str:
    return _stable_id("property_type", (semantic_key, domain_type_id))


def stable_rule_id(
    semantic_key: str,
    rule_kind: str,
    subject_type_id: str,
    output_conclusion_key: str,
) -> str:
    return _stable_id(
        "rule",
        (semantic_key, rule_kind, subject_type_id, output_conclusion_key),
    )


def stable_compilation_issue_id(
    suggestion_id: str,
    code: str,
    payload_schema: str,
) -> str:
    return _stable_id(
        "compilation_issue",
        (suggestion_id, code, payload_schema),
    )


def stable_closure_issue_id(
    code: str,
    owner_id: str,
    field: str,
    referenced_id: str,
) -> str:
    return _stable_id(
        "closure_issue",
        (code, owner_id, field, referenced_id),
    )

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
import hashlib
import json
from typing import Any

from ontology_poc_generator.errors import KnowledgeValidationError
from ontology_poc_generator.identity import stable_binding_id
from ontology_poc_generator.knowledge import (
    KnowledgeOutcome,
    KnowledgeSuggestion,
    SourceRef,
)
from ontology_poc_generator.models import ScenarioParameters


@dataclass(frozen=True)
class InputBinding:
    binding_id: str
    role_key: str
    semantic_key: str
    label: str

    def __post_init__(self) -> None:
        for name in ("binding_id", "role_key", "semantic_key", "label"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise KnowledgeValidationError(f"{name} is required")
            object.__setattr__(self, name, value.strip())


@dataclass(frozen=True)
class DecisionPack:
    schema: str
    scenario: ScenarioParameters
    input_bindings: tuple[InputBinding, ...]
    source_refs: tuple[SourceRef, ...]
    knowledge_outcomes: tuple[KnowledgeOutcome, ...]

    def __post_init__(self) -> None:
        if self.schema != "decision_pack.v1":
            raise KnowledgeValidationError("schema must equal decision_pack.v1")
        if not isinstance(self.scenario, ScenarioParameters):
            raise KnowledgeValidationError("scenario must be ScenarioParameters")
        _require_tuple_of(self.input_bindings, InputBinding, "input_bindings")
        _require_tuple_of(self.source_refs, SourceRef, "source_refs")
        _require_tuple_of(
            self.knowledge_outcomes, KnowledgeOutcome, "knowledge_outcomes"
        )
        _reject_duplicate_ids(
            tuple(item.binding_id for item in self.input_bindings), "binding_id"
        )
        _reject_duplicate_ids(
            tuple(item.source_ref_id for item in self.source_refs), "source_ref_id"
        )
        _reject_duplicate_ids(
            tuple(item.unit_id for item in self.knowledge_outcomes),
            "outcome unit_id",
        )
        _reject_duplicate_ids(
            tuple(
                suggestion.suggestion_id
                for outcome in self.knowledge_outcomes
                for suggestion in outcome.suggestions
            ),
            "suggestion_id across outcomes",
        )

        expected_bindings = tuple(
            sorted(
                (
                    InputBinding(
                        stable_binding_id(
                            self.scenario.decision_key,
                            item.role_key,
                            item.semantic_key,
                        ),
                        item.role_key,
                        item.semantic_key,
                        item.object_label,
                    )
                    for item in self.scenario.object_role_bindings
                ),
                key=lambda item: item.binding_id,
            )
        )
        actual_bindings = tuple(
            sorted(self.input_bindings, key=lambda item: item.binding_id)
        )
        if actual_bindings != expected_bindings:
            raise KnowledgeValidationError(
                "input_bindings must match scenario semantic bindings"
            )

        known_binding_ids = {item.binding_id for item in self.input_bindings}
        known_source_ids = {item.source_ref_id for item in self.source_refs}
        cited_source_ids: set[str] = set()
        for outcome in self.knowledge_outcomes:
            if not set(outcome.input_binding_ids).issubset(known_binding_ids):
                raise KnowledgeValidationError(
                    "outcome references binding outside pack"
                )
            for suggestion in outcome.suggestions:
                cited_source_ids.update(suggestion.source_ref_ids)
                if not set(suggestion.source_ref_ids).issubset(known_source_ids):
                    raise KnowledgeValidationError(
                        "suggestion references source outside pack"
                    )
        if known_source_ids != cited_source_ids:
            raise KnowledgeValidationError(
                "source catalog must exactly match cited source union"
            )
        object.__setattr__(
            self,
            "input_bindings",
            tuple(sorted(self.input_bindings, key=lambda item: item.binding_id)),
        )
        object.__setattr__(
            self,
            "source_refs",
            tuple(sorted(self.source_refs, key=lambda item: item.source_ref_id)),
        )
        object.__setattr__(
            self,
            "knowledge_outcomes",
            tuple(
                sorted(
                    self.knowledge_outcomes,
                    key=lambda item: (
                        item.unit_id,
                        item.unit_version,
                        item.unit_content_hash,
                    ),
                )
            ),
        )


def _require_tuple_of(value: object, item_type: type, field: str) -> None:
    if not isinstance(value, tuple) or any(
        not isinstance(item, item_type) for item in value
    ):
        raise KnowledgeValidationError(
            f"{field} must be a tuple of {item_type.__name__}"
        )


def _reject_duplicate_ids(values: tuple[str, ...], name: str) -> None:
    if len(set(values)) != len(values):
        raise KnowledgeValidationError(f"duplicate {name}")


def _plain_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {field.name: _plain_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    return value


def _canonical_scenario(scenario: ScenarioParameters) -> dict[str, Any]:
    data = _plain_value(scenario)
    collection_fields = (
        "objects",
        "acceptance_questions",
        "participants",
        "constraints",
        "data_sources",
        "desired_actions",
        "relations",
        "object_role_bindings",
        "declared_bridges",
        "readiness_declarations",
    )
    for name in collection_fields:
        data[name] = sorted(
            data[name],
            key=lambda item: json.dumps(
                item, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ),
        )
    return data


def _source_ref_dict(source: SourceRef) -> dict[str, Any]:
    return {
        "source_ref_id": source.source_ref_id,
        "source_kind": source.source_kind.value,
        "title": source.title,
        "locator": source.locator,
        "revision": source.revision,
        "snapshot_sha256": source.snapshot_sha256,
        "caveat": source.caveat,
    }


def _suggestion_dict(suggestion: KnowledgeSuggestion) -> dict[str, Any]:
    return {
        "suggestion_id": suggestion.suggestion_id,
        "unit_id": suggestion.unit_id,
        "unit_version": suggestion.unit_version,
        "unit_content_hash": suggestion.unit_content_hash,
        "contribution_type": suggestion.contribution_type,
        "semantic_key": suggestion.semantic_key,
        "payload_schema": suggestion.payload_schema,
        "payload": {key: value for key, value in suggestion.payload},
        "input_binding_ids": sorted(suggestion.input_binding_ids),
        "source_ref_ids": sorted(suggestion.source_ref_ids),
        "governance_status": suggestion.governance_status,
    }


def _outcome_dict(outcome: KnowledgeOutcome) -> dict[str, Any]:
    return {
        "unit_id": outcome.unit_id,
        "unit_version": outcome.unit_version,
        "unit_content_hash": outcome.unit_content_hash,
        "match_status": outcome.match_status.value,
        "reason_code": outcome.reason_code,
        "input_binding_ids": sorted(outcome.input_binding_ids),
        "suggestions": [
            _suggestion_dict(item)
            for item in sorted(outcome.suggestions, key=lambda item: item.suggestion_id)
        ],
    }


def decision_pack_to_dict(pack: DecisionPack) -> dict[str, Any]:
    """Return the canonical, content-only representation of a DecisionPack."""
    return {
        "schema": pack.schema,
        "scenario": _canonical_scenario(pack.scenario),
        "input_bindings": [
            {
                "binding_id": item.binding_id,
                "role_key": item.role_key,
                "semantic_key": item.semantic_key,
                "label": item.label,
            }
            for item in pack.input_bindings
        ],
        "source_refs": [_source_ref_dict(item) for item in pack.source_refs],
        "knowledge_outcomes": [
            _outcome_dict(item) for item in pack.knowledge_outcomes
        ],
    }


def render_decision_pack_json(pack: DecisionPack) -> str:
    return json.dumps(
        decision_pack_to_dict(pack),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def decision_pack_content_hash(pack: DecisionPack) -> str:
    return hashlib.sha256(render_decision_pack_json(pack).encode("utf-8")).hexdigest()


# Explicit aliases make the canonical nature discoverable without adding formats.
canonical_decision_pack_dict = decision_pack_to_dict
canonical_decision_pack_json = render_decision_pack_json

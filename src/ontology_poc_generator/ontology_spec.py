from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import TypeVar

from ontology_poc_generator.errors import OntologySpecValidationError


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_EnumType = TypeVar("_EnumType", bound=Enum)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OntologySpecValidationError(f"{field} is required")
    return value.strip()


def _enum(value: object, enum_type: type[_EnumType], field: str) -> _EnumType:
    if not isinstance(value, enum_type):
        raise OntologySpecValidationError(
            f"{field} must be {enum_type.__name__}"
        )
    return value


def _tuple(value: object, field: str, item_type: type[object]) -> tuple[object, ...]:
    if not isinstance(value, tuple):
        raise OntologySpecValidationError(f"{field} must be a tuple")
    if any(not isinstance(item, item_type) for item in value):
        raise OntologySpecValidationError(
            f"{field} must contain only {item_type.__name__}"
        )
    return value


def _sorted_unique_elements(
    value: object,
    field: str,
    item_type: type[object],
    id_field: str,
) -> tuple[object, ...]:
    items = _tuple(value, field, item_type)
    identifiers = tuple(getattr(item, id_field) for item in items)
    if len(set(identifiers)) != len(identifiers):
        raise OntologySpecValidationError(f"duplicate {id_field}")
    return tuple(sorted(items, key=lambda item: getattr(item, id_field)))


class SpecStage(str, Enum):
    DRAFT = "draft"


class EvidenceScope(str, Enum):
    SYNTHETIC_DEMO = "synthetic_demo"


class SpecGovernanceStatus(str, Enum):
    CANDIDATE = "candidate"


class SpecOriginKind(str, Enum):
    PROVIDED_INPUT = "provided_input"
    KNOWLEDGE_SUGGESTION = "knowledge_suggestion"


class CompilationIssueSeverity(str, Enum):
    REQUIRES_REVIEW = "requires_review"
    BLOCKING = "blocking"


class CompilationStatus(str, Enum):
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class EntityTypeSpec:
    type_id: str
    role_key: str
    semantic_key: str
    label: str
    governance_status: SpecGovernanceStatus
    origin_kind: SpecOriginKind
    origin_ref_id: str

    def __post_init__(self) -> None:
        for field in ("type_id", "role_key", "semantic_key", "label", "origin_ref_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        _enum(self.governance_status, SpecGovernanceStatus, "governance_status")
        _enum(self.origin_kind, SpecOriginKind, "origin_kind")


@dataclass(frozen=True)
class RelationTypeSpec:
    relation_type_id: str
    semantic_key: str
    predicate: str
    domain_type_id: str
    range_type_id: str
    description: str
    governance_status: SpecGovernanceStatus
    origin_kind: SpecOriginKind
    origin_ref_id: str

    def __post_init__(self) -> None:
        for field in (
            "relation_type_id",
            "semantic_key",
            "predicate",
            "domain_type_id",
            "range_type_id",
            "description",
            "origin_ref_id",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        _enum(self.governance_status, SpecGovernanceStatus, "governance_status")
        _enum(self.origin_kind, SpecOriginKind, "origin_kind")


@dataclass(frozen=True)
class PropertyTypeSpec:
    property_type_id: str
    semantic_key: str
    domain_type_id: str
    value_type: str
    governance_status: SpecGovernanceStatus
    origin_kind: SpecOriginKind
    origin_ref_id: str

    def __post_init__(self) -> None:
        for field in (
            "property_type_id",
            "semantic_key",
            "domain_type_id",
            "value_type",
            "origin_ref_id",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        _enum(self.governance_status, SpecGovernanceStatus, "governance_status")
        _enum(self.origin_kind, SpecOriginKind, "origin_kind")


@dataclass(frozen=True)
class RuleConditionSpec:
    property_type_id: str
    operator: str
    allowed_values: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("property_type_id", "operator"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        values = _tuple(self.allowed_values, "allowed_values", str)
        if not values:
            raise OntologySpecValidationError("allowed_values must not be empty")
        normalized_values = tuple(
            _text(value, f"allowed_values[{index}]")
            for index, value in enumerate(values)
        )
        object.__setattr__(self, "allowed_values", tuple(sorted(normalized_values)))


@dataclass(frozen=True)
class RuleDeclarationSpec:
    rule_id: str
    semantic_key: str
    rule_kind: str
    subject_type_id: str
    conditions: tuple[RuleConditionSpec, ...]
    output_conclusion_key: str
    positive_conclusion_value: str
    negative_conclusion_value: str
    description: str
    governance_status: SpecGovernanceStatus
    origin_suggestion_id: str

    def __post_init__(self) -> None:
        for field in (
            "rule_id",
            "semantic_key",
            "rule_kind",
            "subject_type_id",
            "output_conclusion_key",
            "positive_conclusion_value",
            "negative_conclusion_value",
            "description",
            "origin_suggestion_id",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        conditions = _tuple(self.conditions, "conditions", RuleConditionSpec)
        object.__setattr__(
            self,
            "conditions",
            tuple(
                sorted(
                    conditions,
                    key=lambda item: (
                        item.property_type_id,
                        item.operator,
                        item.allowed_values,
                    ),
                )
            ),
        )
        _enum(self.governance_status, SpecGovernanceStatus, "governance_status")


@dataclass(frozen=True)
class CompilationIssue:
    issue_id: str
    code: str
    severity: CompilationIssueSeverity
    suggestion_id: str
    payload_schema: str
    message: str

    def __post_init__(self) -> None:
        for field in (
            "issue_id",
            "code",
            "suggestion_id",
            "payload_schema",
            "message",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        _enum(self.severity, CompilationIssueSeverity, "severity")


@dataclass(frozen=True)
class OntologySpec:
    schema: str
    decision_key: str
    pack_content_hash: str
    stage: SpecStage
    evidence_scope: EvidenceScope
    governance_status: SpecGovernanceStatus
    input_binding_ids: tuple[str, ...]
    entity_types: tuple[EntityTypeSpec, ...]
    relation_types: tuple[RelationTypeSpec, ...]
    property_types: tuple[PropertyTypeSpec, ...]
    rule_declarations: tuple[RuleDeclarationSpec, ...]
    compilation_issues: tuple[CompilationIssue, ...]

    def __post_init__(self) -> None:
        schema = _text(self.schema, "schema")
        if schema != "ontology_spec.v1":
            raise OntologySpecValidationError("schema must be ontology_spec.v1")
        object.__setattr__(self, "schema", schema)
        object.__setattr__(
            self, "decision_key", _text(self.decision_key, "decision_key")
        )
        pack_hash = _text(self.pack_content_hash, "pack_content_hash")
        if not _SHA256_PATTERN.fullmatch(pack_hash):
            raise OntologySpecValidationError(
                "pack_content_hash must be a SHA-256 hex digest"
            )
        object.__setattr__(self, "pack_content_hash", pack_hash)
        _enum(self.stage, SpecStage, "stage")
        _enum(self.evidence_scope, EvidenceScope, "evidence_scope")
        _enum(self.governance_status, SpecGovernanceStatus, "governance_status")

        input_binding_ids = _tuple(
            self.input_binding_ids, "input_binding_ids", str
        )
        normalized_binding_ids = tuple(
            _text(binding_id, f"input_binding_ids[{index}]")
            for index, binding_id in enumerate(input_binding_ids)
        )
        if len(set(normalized_binding_ids)) != len(normalized_binding_ids):
            raise OntologySpecValidationError("duplicate input_binding_id")
        object.__setattr__(
            self, "input_binding_ids", tuple(sorted(normalized_binding_ids))
        )
        object.__setattr__(
            self,
            "entity_types",
            _sorted_unique_elements(
                self.entity_types, "entity_types", EntityTypeSpec, "type_id"
            ),
        )
        object.__setattr__(
            self,
            "relation_types",
            _sorted_unique_elements(
                self.relation_types,
                "relation_types",
                RelationTypeSpec,
                "relation_type_id",
            ),
        )
        object.__setattr__(
            self,
            "property_types",
            _sorted_unique_elements(
                self.property_types,
                "property_types",
                PropertyTypeSpec,
                "property_type_id",
            ),
        )
        object.__setattr__(
            self,
            "rule_declarations",
            _sorted_unique_elements(
                self.rule_declarations,
                "rule_declarations",
                RuleDeclarationSpec,
                "rule_id",
            ),
        )
        object.__setattr__(
            self,
            "compilation_issues",
            _sorted_unique_elements(
                self.compilation_issues,
                "compilation_issues",
                CompilationIssue,
                "issue_id",
            ),
        )

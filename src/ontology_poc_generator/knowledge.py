from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import Mapping

from ontology_poc_generator.errors import KnowledgeValidationError


_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {"threshold", "expression", "result", "action", "writeback"}
)


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise KnowledgeValidationError(f"{field} is required")
    return value.strip()


def _sha256(value: object, field: str) -> str:
    digest = _text(value, field)
    if not _SHA256_PATTERN.fullmatch(digest):
        raise KnowledgeValidationError(f"{field} must be a SHA-256 hex digest")
    return digest.lower()


def _string_tuple(value: object, field: str, *, required: bool = False) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise KnowledgeValidationError(f"{field} must be a list of strings")
    result = tuple(_text(item, f"{field}[{index}]") for index, item in enumerate(value))
    if required and not result:
        raise KnowledgeValidationError(f"{field} must contain at least one item")
    return result


class SourceKind(str, Enum):
    PROVIDED_INPUT = "provided_input"
    AUTHORITATIVE_REFERENCE = "authoritative_reference"
    IMPLEMENTED_ARTIFACT = "implemented_artifact"
    OBSERVED_CASE = "observed_case"
    PRACTITIONER_NOTE = "practitioner_note"
    SYNTHETIC_EXAMPLE = "synthetic_example"


@dataclass(frozen=True)
class SourceRef:
    source_ref_id: str
    source_kind: SourceKind
    title: str
    locator: str
    revision: str
    snapshot_sha256: str
    caveat: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_ref_id", _text(self.source_ref_id, "source_ref_id"))
        if not isinstance(self.source_kind, SourceKind):
            raise KnowledgeValidationError("source_kind must be a known SourceKind")
        for field in ("title", "locator", "revision", "caveat"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self,
            "snapshot_sha256",
            _sha256(self.snapshot_sha256, "snapshot_sha256"),
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, object], index: int) -> "SourceRef":
        if not isinstance(data, Mapping):
            raise KnowledgeValidationError(f"sources[{index}] must be an object")
        raw_kind = data.get("source_kind")
        try:
            source_kind = SourceKind(raw_kind)
        except (TypeError, ValueError) as error:
            raise KnowledgeValidationError(
                f"sources[{index}].source_kind must be a known source kind"
            ) from error
        return cls(
            source_ref_id=_text(data.get("source_ref_id"), f"sources[{index}].source_ref_id"),
            source_kind=source_kind,
            title=_text(data.get("title"), f"sources[{index}].title"),
            locator=_text(data.get("locator"), f"sources[{index}].locator"),
            revision=_text(data.get("revision"), f"sources[{index}].revision"),
            snapshot_sha256=_sha256(
                data.get("snapshot_sha256"),
                f"sources[{index}].snapshot_sha256",
            ),
            caveat=_text(data.get("caveat"), f"sources[{index}].caveat"),
        )


@dataclass(frozen=True)
class KnowledgeSuggestion:
    suggestion_id: str
    unit_id: str
    unit_version: str
    unit_content_hash: str
    contribution_type: str
    semantic_key: str
    payload: tuple[tuple[str, str], ...]
    input_binding_ids: tuple[str, ...]
    source_ref_ids: tuple[str, ...]
    governance_status: str = "candidate"

    def __post_init__(self) -> None:
        for field in (
            "suggestion_id",
            "unit_id",
            "unit_version",
            "contribution_type",
            "semantic_key",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self,
            "unit_content_hash",
            _sha256(self.unit_content_hash, "unit_content_hash"),
        )
        if self.governance_status != "candidate":
            raise KnowledgeValidationError("governance_status must be candidate")
        if not isinstance(self.payload, tuple):
            raise KnowledgeValidationError("payload must be an immutable tuple")
        normalized_payload: list[tuple[str, str]] = []
        for index, item in enumerate(self.payload):
            if not isinstance(item, tuple) or len(item) != 2:
                raise KnowledgeValidationError(f"payload[{index}] must be a key/value pair")
            key = _text(item[0], f"payload[{index}].key")
            value = _text(item[1], f"payload[{index}].value")
            if key.casefold() in _FORBIDDEN_PAYLOAD_KEYS:
                raise KnowledgeValidationError(f"payload key {key} is forbidden")
            normalized_payload.append((key, value))
        if len({key for key, _ in normalized_payload}) != len(normalized_payload):
            raise KnowledgeValidationError("payload keys must be unique")
        object.__setattr__(self, "payload", tuple(sorted(normalized_payload)))
        object.__setattr__(
            self,
            "input_binding_ids",
            _string_tuple(self.input_binding_ids, "input_binding_ids"),
        )
        object.__setattr__(
            self,
            "source_ref_ids",
            _string_tuple(self.source_ref_ids, "source_ref_ids", required=True),
        )

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, object],
        index: int,
        *,
        unit_id: str,
        unit_version: str,
        unit_content_hash: str,
    ) -> "KnowledgeSuggestion":
        if not isinstance(data, Mapping):
            raise KnowledgeValidationError(
                f"suggestion_templates[{index}] must be an object"
            )
        raw_payload = data.get("payload")
        if not isinstance(raw_payload, Mapping):
            raise KnowledgeValidationError(
                f"suggestion_templates[{index}].payload must be an object"
            )
        return cls(
            suggestion_id=_text(
                data.get("suggestion_id"),
                f"suggestion_templates[{index}].suggestion_id",
            ),
            unit_id=unit_id,
            unit_version=unit_version,
            unit_content_hash=unit_content_hash,
            contribution_type=_text(
                data.get("contribution_type"),
                f"suggestion_templates[{index}].contribution_type",
            ),
            semantic_key=_text(
                data.get("semantic_key"),
                f"suggestion_templates[{index}].semantic_key",
            ),
            payload=tuple((key, value) for key, value in raw_payload.items()),
            input_binding_ids=_string_tuple(
                data.get("input_binding_ids", []),
                f"suggestion_templates[{index}].input_binding_ids",
            ),
            source_ref_ids=_string_tuple(
                data.get("source_ref_ids", []),
                f"suggestion_templates[{index}].source_ref_ids",
                required=True,
            ),
            governance_status=data.get("governance_status", "candidate"),
        )


@dataclass(frozen=True)
class KnowledgeUnit:
    unit_id: str
    unit_version: str
    decision_key: str
    unit_content_hash: str
    source_refs: tuple[SourceRef, ...]
    suggestion_templates: tuple[KnowledgeSuggestion, ...]

    def __post_init__(self) -> None:
        for field in ("unit_id", "unit_version", "decision_key"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self,
            "unit_content_hash",
            _sha256(self.unit_content_hash, "unit_content_hash"),
        )
        if not isinstance(self.source_refs, tuple) or any(
            not isinstance(source, SourceRef) for source in self.source_refs
        ):
            raise KnowledgeValidationError("source_refs must be a tuple of SourceRef")
        if not isinstance(self.suggestion_templates, tuple) or any(
            not isinstance(template, KnowledgeSuggestion)
            for template in self.suggestion_templates
        ):
            raise KnowledgeValidationError(
                "suggestion_templates must be a tuple of KnowledgeSuggestion"
            )
        suggestion_ids = tuple(
            template.suggestion_id for template in self.suggestion_templates
        )
        if len(set(suggestion_ids)) != len(suggestion_ids):
            raise KnowledgeValidationError("duplicate suggestion_id")
        source_ids = tuple(source.source_ref_id for source in self.source_refs)
        if len(set(source_ids)) != len(source_ids):
            raise KnowledgeValidationError("duplicate source_ref_id")
        known_source_ids = set(source_ids)
        for template in self.suggestion_templates:
            if template.unit_id != self.unit_id:
                raise KnowledgeValidationError("template unit_id does not match unit")
            if template.unit_version != self.unit_version:
                raise KnowledgeValidationError("template unit_version does not match unit")
            if template.unit_content_hash != self.unit_content_hash:
                raise KnowledgeValidationError("template unit_content_hash does not match unit")
            unknown = set(template.source_ref_ids) - known_source_ids
            if unknown:
                raise KnowledgeValidationError(
                    f"template references unknown source_ref_id: {sorted(unknown)[0]}"
                )

    @classmethod
    def from_dict(
        cls,
        data: Mapping[str, object],
        *,
        unit_content_hash: str,
    ) -> "KnowledgeUnit":
        if not isinstance(data, Mapping):
            raise KnowledgeValidationError("knowledge unit must be an object")
        unit_id = _text(data.get("unit_id"), "unit_id")
        unit_version = _text(data.get("unit_version"), "unit_version")
        decision_key = _text(data.get("decision_key"), "decision_key")
        digest = _sha256(unit_content_hash, "unit_content_hash")
        raw_sources = data.get("sources")
        if not isinstance(raw_sources, list):
            raise KnowledgeValidationError("sources must be a list")
        sources = tuple(
            SourceRef.from_dict(source, index)
            for index, source in enumerate(raw_sources)
        )
        raw_templates = data.get("suggestion_templates")
        if not isinstance(raw_templates, list):
            raise KnowledgeValidationError("suggestion_templates must be a list")
        templates = tuple(
            KnowledgeSuggestion.from_dict(
                template,
                index,
                unit_id=unit_id,
                unit_version=unit_version,
                unit_content_hash=digest,
            )
            for index, template in enumerate(raw_templates)
        )
        return cls(
            unit_id=unit_id,
            unit_version=unit_version,
            decision_key=decision_key,
            unit_content_hash=digest,
            source_refs=sources,
            suggestion_templates=templates,
        )

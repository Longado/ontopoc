from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
from typing import Mapping

from ontology_poc_generator.errors import KnowledgeValidationError
from ontology_poc_generator.identity import stable_binding_id, stable_suggestion_id
from ontology_poc_generator.models import ReadinessStatus, ScenarioParameters


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


class MatchStatus(str, Enum):
    APPLICABLE = "applicable"
    NOT_APPLICABLE = "not_applicable"
    INSUFFICIENT_INFORMATION = "insufficient_information"


@dataclass(frozen=True)
class InputBinding:
    binding_id: str
    semantic_key: str
    label: str

    def __post_init__(self) -> None:
        for field in ("binding_id", "semantic_key", "label"):
            object.__setattr__(self, field, _text(getattr(self, field), field))


@dataclass(frozen=True)
class RequiredBridge:
    semantic_key: str
    source_role_key: str
    predicate: str
    target_role_key: str

    def __post_init__(self) -> None:
        for field in (
            "semantic_key",
            "source_role_key",
            "predicate",
            "target_role_key",
        ):
            object.__setattr__(self, field, _text(getattr(self, field), field))

    @classmethod
    def from_dict(cls, data: Mapping[str, object], index: int) -> "RequiredBridge":
        if not isinstance(data, Mapping):
            raise KnowledgeValidationError(
                f"applicability.required_bridges[{index}] must be an object"
            )
        prefix = f"applicability.required_bridges[{index}]"
        return cls(
            semantic_key=_text(data.get("semantic_key"), f"{prefix}.semantic_key"),
            source_role_key=_text(
                data.get("source_role_key"), f"{prefix}.source_role_key"
            ),
            predicate=_text(data.get("predicate"), f"{prefix}.predicate"),
            target_role_key=_text(
                data.get("target_role_key"), f"{prefix}.target_role_key"
            ),
        )


@dataclass(frozen=True)
class ApplicabilitySpec:
    required_role_keys: tuple[str, ...] = ()
    required_bridges: tuple[RequiredBridge, ...] = ()
    readiness_requirement_keys: tuple[str, ...] = ()
    decision_mismatch_reason_code: str = ""
    missing_required_role_reason_code: str = ""
    missing_required_bridge_reason_code: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "required_role_keys",
            _string_tuple(self.required_role_keys, "required_role_keys"),
        )
        normalized_role_keys = tuple(
            item.casefold() for item in self.required_role_keys
        )
        if len(set(normalized_role_keys)) != len(normalized_role_keys):
            raise KnowledgeValidationError("duplicate required_role_key")
        if not isinstance(self.required_bridges, tuple) or any(
            not isinstance(bridge, RequiredBridge) for bridge in self.required_bridges
        ):
            raise KnowledgeValidationError(
                "required_bridges must be a tuple of RequiredBridge"
            )
        bridge_semantic_keys = tuple(
            bridge.semantic_key.casefold() for bridge in self.required_bridges
        )
        if len(set(bridge_semantic_keys)) != len(bridge_semantic_keys):
            raise KnowledgeValidationError(
                "duplicate required bridge semantic_key"
            )
        known_roles = set(normalized_role_keys)
        for bridge in self.required_bridges:
            if (
                bridge.source_role_key.casefold() not in known_roles
                or bridge.target_role_key.casefold() not in known_roles
            ):
                raise KnowledgeValidationError(
                    f"bridge references unknown role: {bridge.semantic_key}"
                )
        object.__setattr__(
            self,
            "readiness_requirement_keys",
            _string_tuple(
                self.readiness_requirement_keys,
                "readiness_requirement_keys",
            ),
        )
        normalized_readiness_keys = tuple(
            item.casefold() for item in self.readiness_requirement_keys
        )
        if len(set(normalized_readiness_keys)) != len(normalized_readiness_keys):
            raise KnowledgeValidationError("duplicate readiness_requirement_key")
        reason_fields = (
            "decision_mismatch_reason_code",
            "missing_required_role_reason_code",
            "missing_required_bridge_reason_code",
        )
        has_contract = bool(
            self.required_role_keys
            or self.required_bridges
            or self.readiness_requirement_keys
            or any(getattr(self, field) for field in reason_fields)
        )
        if has_contract:
            for field in reason_fields:
                object.__setattr__(self, field, _text(getattr(self, field), field))

    @classmethod
    def from_dict(cls, data: Mapping[str, object]) -> "ApplicabilitySpec":
        if not isinstance(data, Mapping):
            raise KnowledgeValidationError("applicability must be an object")
        raw_bridges = data.get("required_bridges", [])
        if not isinstance(raw_bridges, list):
            raise KnowledgeValidationError(
                "applicability.required_bridges must be a list"
            )
        return cls(
            required_role_keys=_string_tuple(
                data.get("required_role_keys", []),
                "applicability.required_role_keys",
            ),
            required_bridges=tuple(
                RequiredBridge.from_dict(bridge, index)
                for index, bridge in enumerate(raw_bridges)
            ),
            readiness_requirement_keys=_string_tuple(
                data.get("readiness_requirement_keys", []),
                "applicability.readiness_requirement_keys",
            ),
            decision_mismatch_reason_code=_text(
                data.get("decision_mismatch_reason_code"),
                "applicability.decision_mismatch_reason_code",
            ),
            missing_required_role_reason_code=_text(
                data.get("missing_required_role_reason_code"),
                "applicability.missing_required_role_reason_code",
            ),
            missing_required_bridge_reason_code=_text(
                data.get("missing_required_bridge_reason_code"),
                "applicability.missing_required_bridge_reason_code",
            ),
        )


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
    applicability: ApplicabilitySpec = ApplicabilitySpec()

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
        if not isinstance(self.applicability, ApplicabilitySpec):
            raise KnowledgeValidationError(
                "applicability must be an ApplicabilitySpec"
            )
        suggestion_ids = tuple(
            template.suggestion_id for template in self.suggestion_templates
        )
        if len(set(suggestion_ids)) != len(suggestion_ids):
            raise KnowledgeValidationError("duplicate suggestion_id")
        suggestion_identity_seeds = tuple(
            (
                template.semantic_key.casefold(),
                tuple(role.casefold() for role in template.input_binding_ids),
            )
            for template in self.suggestion_templates
        )
        if len(set(suggestion_identity_seeds)) != len(suggestion_identity_seeds):
            raise KnowledgeValidationError("duplicate suggestion identity seed")
        source_ids = tuple(source.source_ref_id for source in self.source_refs)
        if len(set(source_ids)) != len(source_ids):
            raise KnowledgeValidationError("duplicate source_ref_id")
        known_source_ids = set(source_ids)
        known_roles = {
            role.casefold() for role in self.applicability.required_role_keys
        }
        readiness_requirements = set(
            key.casefold()
            for key in self.applicability.readiness_requirement_keys
        )
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
            unknown_roles = {
                role.casefold() for role in template.input_binding_ids
            } - known_roles
            if unknown_roles:
                raise KnowledgeValidationError(
                    "template references unknown applicability role: "
                    f"{sorted(unknown_roles)[0]}"
                )
            if template.contribution_type == "readiness_gap":
                requirement_key = dict(template.payload).get("requirement_key")
                if (
                    not isinstance(requirement_key, str)
                    or requirement_key.casefold() not in readiness_requirements
                ):
                    raise KnowledgeValidationError(
                        "readiness gap references unknown readiness requirement"
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
        raw_applicability = data.get("applicability")
        applicability = (
            ApplicabilitySpec.from_dict(raw_applicability)
            if raw_applicability is not None
            else ApplicabilitySpec()
        )
        return cls(
            unit_id=unit_id,
            unit_version=unit_version,
            decision_key=decision_key,
            unit_content_hash=digest,
            source_refs=sources,
            suggestion_templates=templates,
            applicability=applicability,
        )


def load_knowledge_unit(path: str | Path) -> KnowledgeUnit:
    package_path = Path(path)
    with package_path.open("r", encoding="utf-8") as stream:
        data = json.load(stream)
    canonical = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    content_hash = hashlib.sha256(canonical).hexdigest()
    return KnowledgeUnit.from_dict(data, unit_content_hash=content_hash)


@dataclass(frozen=True)
class KnowledgeOutcome:
    unit_id: str
    unit_version: str
    unit_content_hash: str
    match_status: MatchStatus
    reason_code: str
    input_binding_ids: tuple[str, ...]
    suggestions: tuple[KnowledgeSuggestion, ...]

    def __post_init__(self) -> None:
        for field in ("unit_id", "unit_version", "reason_code"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        object.__setattr__(
            self,
            "unit_content_hash",
            _sha256(self.unit_content_hash, "unit_content_hash"),
        )
        if not isinstance(self.match_status, MatchStatus):
            raise KnowledgeValidationError("match_status must be a MatchStatus")
        object.__setattr__(
            self,
            "input_binding_ids",
            _string_tuple(self.input_binding_ids, "input_binding_ids"),
        )
        if not isinstance(self.suggestions, tuple) or any(
            not isinstance(item, KnowledgeSuggestion) for item in self.suggestions
        ):
            raise KnowledgeValidationError(
                "suggestions must be a tuple of KnowledgeSuggestion"
            )
        if self.match_status is not MatchStatus.APPLICABLE and self.suggestions:
            raise KnowledgeValidationError(
                "non-applicable outcome cannot carry suggestions"
            )
        if self.match_status is MatchStatus.APPLICABLE:
            suggestion_ids = tuple(
                item.suggestion_id for item in self.suggestions
            )
            if len(set(suggestion_ids)) != len(suggestion_ids):
                raise KnowledgeValidationError("suggestion_id must be unique")
            expected_provenance = (
                self.unit_id,
                self.unit_version,
                self.unit_content_hash,
            )
            for suggestion in self.suggestions:
                actual_provenance = (
                    suggestion.unit_id,
                    suggestion.unit_version,
                    suggestion.unit_content_hash,
                )
                if actual_provenance != expected_provenance:
                    raise KnowledgeValidationError(
                        "suggestion provenance must match outcome"
                    )


def _normalized(value: str) -> str:
    return value.strip().casefold()


def _empty_outcome(
    unit: KnowledgeUnit,
    status: MatchStatus,
    reason_code: str,
) -> KnowledgeOutcome:
    return KnowledgeOutcome(
        unit_id=unit.unit_id,
        unit_version=unit.unit_version,
        unit_content_hash=unit.unit_content_hash,
        match_status=status,
        reason_code=reason_code,
        input_binding_ids=(),
        suggestions=(),
    )


def match_knowledge_unit(
    scenario: ScenarioParameters,
    unit: KnowledgeUnit,
) -> KnowledgeOutcome:
    """Match a declarative unit using only controlled semantic input fields."""
    applicability = unit.applicability
    if _normalized(scenario.decision_key) != _normalized(unit.decision_key):
        return _empty_outcome(
            unit,
            MatchStatus.NOT_APPLICABLE,
            applicability.decision_mismatch_reason_code or "decision_key_mismatch",
        )

    roles_by_key = {
        _normalized(binding.role_key): binding
        for binding in scenario.object_role_bindings
    }
    required_roles = tuple(
        _normalized(role_key) for role_key in applicability.required_role_keys
    )
    if any(role_key not in roles_by_key for role_key in required_roles):
        return _empty_outcome(
            unit,
            MatchStatus.INSUFFICIENT_INFORMATION,
            applicability.missing_required_role_reason_code or "required_role_missing",
        )

    declared_bridges = {
        (
            _normalized(bridge.semantic_key),
            _normalized(bridge.source_role_key),
            _normalized(bridge.predicate),
            _normalized(bridge.target_role_key),
        )
        for bridge in scenario.declared_bridges
    }
    for bridge in applicability.required_bridges:
        required_bridge = (
            _normalized(bridge.semantic_key),
            _normalized(bridge.source_role_key),
            _normalized(bridge.predicate),
            _normalized(bridge.target_role_key),
        )
        if required_bridge not in declared_bridges:
            return _empty_outcome(
                unit,
                MatchStatus.INSUFFICIENT_INFORMATION,
                applicability.missing_required_bridge_reason_code
                or "required_bridge_missing",
            )

    binding_ids_by_role = {
        role_key: stable_binding_id(
            scenario.decision_key,
            binding.role_key,
            binding.semantic_key,
        )
        for role_key, binding in roles_by_key.items()
    }
    relevant_binding_ids = tuple(
        binding_ids_by_role[role_key] for role_key in required_roles
    )
    readiness_by_key = {
        _normalized(item.requirement_key): item.status
        for item in scenario.readiness_declarations
    }

    suggestions: list[KnowledgeSuggestion] = []
    for template in unit.suggestion_templates:
        payload = dict(template.payload)
        if template.contribution_type == "readiness_gap":
            requirement_key = _normalized(payload["requirement_key"])
            if readiness_by_key.get(requirement_key) is ReadinessStatus.READY:
                continue
        instantiated_binding_ids = tuple(
            binding_ids_by_role[_normalized(role_key)]
            for role_key in template.input_binding_ids
        )
        suggestions.append(
            KnowledgeSuggestion(
                suggestion_id=stable_suggestion_id(
                    unit.unit_id,
                    unit.unit_version,
                    _normalized(template.semantic_key),
                    instantiated_binding_ids,
                ),
                unit_id=unit.unit_id,
                unit_version=unit.unit_version,
                unit_content_hash=unit.unit_content_hash,
                contribution_type=template.contribution_type,
                semantic_key=template.semantic_key,
                payload=template.payload,
                input_binding_ids=instantiated_binding_ids,
                source_ref_ids=template.source_ref_ids,
                governance_status="candidate",
            )
        )

    return KnowledgeOutcome(
        unit_id=unit.unit_id,
        unit_version=unit.unit_version,
        unit_content_hash=unit.unit_content_hash,
        match_status=MatchStatus.APPLICABLE,
        reason_code="applicable",
        input_binding_ids=relevant_binding_ids,
        suggestions=tuple(suggestions),
    )

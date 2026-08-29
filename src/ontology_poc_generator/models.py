from __future__ import annotations

from dataclasses import dataclass

from ontology_poc_generator.errors import ScenarioValidationError


def _validated_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioValidationError(f"{field} is required")
    return value.strip()


def _required_text(data: dict, field: str, error_field: str | None = None) -> str:
    return _validated_text(data.get(field), error_field or field)


def _validated_data_source_status(value: object, field: str) -> str:
    if not isinstance(value, str) or value not in {
        "available",
        "to_confirm",
        "unavailable",
    }:
        raise ScenarioValidationError(
            f"{field} must be available, to_confirm, or unavailable"
        )
    return value


def _validated_boolean(value: object, field: str) -> bool:
    if type(value) is not bool:
        raise ScenarioValidationError(f"{field} must be a boolean")
    return value


def _string_tuple(data: dict, field: str) -> tuple[str, ...]:
    value = data.get(field, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ScenarioValidationError(f"{field} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


@dataclass(frozen=True)
class DataSource:
    name: str
    type: str
    status: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _validated_text(self.name, "name"))
        object.__setattr__(self, "type", _validated_text(self.type, "type"))
        object.__setattr__(
            self,
            "status",
            _validated_data_source_status(self.status, "status"),
        )

    @classmethod
    def from_dict(cls, data: dict, index: int) -> "DataSource":
        prefix = f"data_sources[{index}]"
        return cls(
            name=_required_text(data, "name", f"{prefix}.name"),
            type=_required_text(data, "type", f"{prefix}.type"),
            status=_validated_data_source_status(data.get("status"), f"{prefix}.status"),
        )


def _validated_data_sources(value: object) -> tuple[DataSource, ...]:
    if not isinstance(value, tuple):
        raise ScenarioValidationError("data_sources must be a tuple of DataSource")
    for index, source in enumerate(value):
        if not isinstance(source, DataSource):
            raise ScenarioValidationError(f"data_sources[{index}] must be a DataSource")
    return value


@dataclass(frozen=True)
class ScenarioParameters:
    industry: str
    scene_name: str
    business_decision: str
    decision_owner: str
    trigger: str
    objects: tuple[str, ...]
    acceptance_questions: tuple[str, ...]
    participants: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    data_sources: tuple[DataSource, ...] = ()
    desired_actions: tuple[str, ...] = ()
    customer_data_available: bool = False
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data_sources",
            _validated_data_sources(self.data_sources),
        )
        object.__setattr__(
            self,
            "customer_data_available",
            _validated_boolean(
                self.customer_data_available,
                "customer_data_available",
            ),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "ScenarioParameters":
        objects = _string_tuple(data, "objects")
        if len(objects) < 2:
            raise ScenarioValidationError("objects must contain at least two items")
        questions = _string_tuple(data, "acceptance_questions")
        if not questions:
            raise ScenarioValidationError("acceptance_questions must contain at least one item")
        raw_sources = data.get("data_sources", [])
        if not isinstance(raw_sources, list) or any(
            not isinstance(item, dict) for item in raw_sources
        ):
            raise ScenarioValidationError("data_sources must be a list of objects")
        return cls(
            industry=_required_text(data, "industry"),
            scene_name=_required_text(data, "scene_name"),
            business_decision=_required_text(data, "business_decision"),
            decision_owner=_required_text(data, "decision_owner"),
            trigger=_required_text(data, "trigger"),
            objects=objects,
            acceptance_questions=questions,
            participants=_string_tuple(data, "participants"),
            constraints=_string_tuple(data, "constraints"),
            data_sources=tuple(
                DataSource.from_dict(item, index)
                for index, item in enumerate(raw_sources)
            ),
            desired_actions=_string_tuple(data, "desired_actions"),
            customer_data_available=data.get("customer_data_available", False),
            notes=str(data.get("notes", "")).strip(),
        )


@dataclass(frozen=True)
class Proposal:
    industry: str
    scene_name: str
    primary_decision: str
    decision_owner: str
    trigger: str
    object_types: tuple[str, ...]
    relation_candidates: tuple[str, ...]
    constraints: tuple[str, ...]
    data_sources: tuple[DataSource, ...]
    data_gaps: tuple[str, ...]
    desired_actions: tuple[str, ...]
    acceptance_questions: tuple[str, ...]
    decision_loop: tuple[str, ...]
    responsibility_boundaries: tuple[str, ...]
    evidence_mode: str
    notes: str

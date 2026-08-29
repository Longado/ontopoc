from __future__ import annotations

from dataclasses import dataclass

from ontology_poc_generator.errors import ScenarioValidationError


def _required_text(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ScenarioValidationError(f"{field} is required")
    return value.strip()


def _string_tuple(data: dict, field: str) -> tuple[str, ...]:
    value = data.get(field, [])
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ScenarioValidationError(f"{field} must be a list of strings")
    return tuple(item.strip() for item in value if item.strip())


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
    data_sources: tuple[dict, ...] = ()
    desired_actions: tuple[str, ...] = ()
    customer_data_available: bool = False
    notes: str = ""

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
            data_sources=tuple(dict(item) for item in raw_sources),
            desired_actions=_string_tuple(data, "desired_actions"),
            customer_data_available=bool(data.get("customer_data_available", False)),
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
    data_sources: tuple[dict, ...]
    data_gaps: tuple[str, ...]
    desired_actions: tuple[str, ...]
    acceptance_questions: tuple[str, ...]
    decision_loop: tuple[str, ...]
    responsibility_boundaries: tuple[str, ...]
    evidence_mode: str
    notes: str

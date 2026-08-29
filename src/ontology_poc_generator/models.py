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


@dataclass(frozen=True)
class Relation:
    source: str
    predicate: str
    target: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", _validated_text(self.source, "source"))
        object.__setattr__(
            self,
            "predicate",
            _validated_text(self.predicate, "predicate"),
        )
        object.__setattr__(self, "target", _validated_text(self.target, "target"))

    @classmethod
    def from_dict(cls, data: dict, index: int) -> "Relation":
        prefix = f"relations[{index}]"
        return cls(
            source=_required_text(data, "source", f"{prefix}.source"),
            predicate=_required_text(data, "predicate", f"{prefix}.predicate"),
            target=_required_text(data, "target", f"{prefix}.target"),
        )


def _validated_data_sources(value: object) -> tuple[DataSource, ...]:
    if not isinstance(value, tuple):
        raise ScenarioValidationError("data_sources must be a tuple of DataSource")
    for index, source in enumerate(value):
        if not isinstance(source, DataSource):
            raise ScenarioValidationError(f"data_sources[{index}] must be a DataSource")
    return value


def _validated_relations(value: object) -> tuple[Relation, ...]:
    if not isinstance(value, tuple):
        raise ScenarioValidationError("relations must be a tuple of Relation")
    for index, relation in enumerate(value):
        if not isinstance(relation, Relation):
            raise ScenarioValidationError(f"relations[{index}] must be a Relation")
    return value


_DEFAULT_PLANNED_CAPABILITIES = (
    "POC 计划（待验证，尚未生成）：规则求值、影响分析和可运行演示",
    "POC 计划（待验证，尚未生成）：Agent 编排、任务创建、版本与决策轨迹、验收矩阵和修正记录",
)
_DEFAULT_ACCEPTANCE_QUESTIONS_STATUS = "候选验收问题"
_DEFAULT_READINESS_GAP = (
    "尚未形成完整通过条件：当前缺少输入、步骤、预期结果、证据和责任人；"
    "需在 POC 计划中补齐并验证。"
)


def _current_draft_contents(relation_candidates: tuple[str, ...]) -> str:
    return (
        "对象、显式关系、约束和数据缺口草案"
        if relation_candidates
        else "对象、约束和数据缺口草案；关系信息不足"
    )


def _default_current_capabilities(
    relation_candidates: tuple[str, ...],
) -> tuple[str, ...]:
    return (f"当前已生成：业务决策卡、{_current_draft_contents(relation_candidates)}",)


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
    relations: tuple[Relation, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "data_sources",
            _validated_data_sources(self.data_sources),
        )
        object.__setattr__(self, "relations", _validated_relations(self.relations))
        for index, relation in enumerate(self.relations):
            if relation.source not in self.objects:
                raise ScenarioValidationError(
                    f"relations[{index}].source must reference an object"
                )
            if relation.target not in self.objects:
                raise ScenarioValidationError(
                    f"relations[{index}].target must reference an object"
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
        raw_relations = data.get("relations", [])
        if not isinstance(raw_relations, list) or any(
            not isinstance(item, dict) for item in raw_relations
        ):
            raise ScenarioValidationError("relations must be a list of objects")
        return cls(
            industry=_required_text(data, "industry"),
            scene_name=_required_text(data, "scene_name"),
            business_decision=_required_text(data, "business_decision"),
            decision_owner=_required_text(data, "decision_owner"),
            trigger=_required_text(data, "trigger"),
            objects=objects,
            acceptance_questions=questions,
            relations=tuple(
                Relation.from_dict(item, index)
                for index, item in enumerate(raw_relations)
            ),
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
    current_capabilities: tuple[str, ...] = ()
    planned_capabilities: tuple[str, ...] = ()
    acceptance_questions_status: str = ""
    readiness_gap: str = ""

    def __post_init__(self) -> None:
        if not self.current_capabilities:
            object.__setattr__(
                self,
                "current_capabilities",
                _default_current_capabilities(self.relation_candidates),
            )
        if not self.planned_capabilities:
            object.__setattr__(self, "planned_capabilities", _DEFAULT_PLANNED_CAPABILITIES)
        if not self.acceptance_questions_status:
            object.__setattr__(
                self,
                "acceptance_questions_status",
                _DEFAULT_ACCEPTANCE_QUESTIONS_STATUS,
            )
        if not self.readiness_gap:
            object.__setattr__(self, "readiness_gap", _DEFAULT_READINESS_GAP)

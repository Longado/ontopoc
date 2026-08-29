from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
from typing import TYPE_CHECKING

from ontology_poc_generator.errors import ScenarioValidationError

if TYPE_CHECKING:
    from ontology_poc_generator.decision_pack import InputBinding
    from ontology_poc_generator.knowledge import KnowledgeOutcome, SourceRef


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


def _validated_string_tuple(
    value: object,
    field: str,
    *,
    minimum_items: int = 0,
) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise ScenarioValidationError(f"{field} must be a tuple of strings")
    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ScenarioValidationError(f"{field}[{index}] must be a non-empty string")
        normalized.append(item.strip())
    if len(normalized) < minimum_items:
        if field == "objects":
            raise ScenarioValidationError("objects must contain at least two items")
        raise ScenarioValidationError(
            f"{field} must contain at least {minimum_items} item"
        )
    return tuple(normalized)


_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
_SEMANTIC_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]*$")
_PREDICATE_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _validated_key(value: object, field: str, *, optional: bool = False) -> str:
    if optional and (value is None or value == ""):
        return ""
    key = _validated_text(value, field)
    if not _KEY_PATTERN.fullmatch(key):
        raise ScenarioValidationError(
            f"{field} must be a lowercase semantic key"
        )
    return key


def _validated_semantic_key(value: object, field: str) -> str:
    key = _validated_text(value, field)
    if not _SEMANTIC_KEY_PATTERN.fullmatch(key):
        raise ScenarioValidationError(f"{field} must be a semantic key")
    return key


def _validated_predicate(value: object, field: str) -> str:
    predicate = _validated_text(value, field)
    if not _PREDICATE_PATTERN.fullmatch(predicate):
        raise ScenarioValidationError(f"{field} must be a predicate key")
    return predicate.upper()


class ReadinessStatus(str, Enum):
    READY = "ready"
    TO_CONFIRM = "to_confirm"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class ObjectRoleBinding:
    role_key: str
    semantic_key: str
    object_label: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "role_key", _validated_key(self.role_key, "role_key"))
        object.__setattr__(
            self,
            "semantic_key",
            _validated_semantic_key(self.semantic_key, "semantic_key"),
        )
        object.__setattr__(
            self,
            "object_label",
            _validated_text(self.object_label, "object_label"),
        )

    @classmethod
    def from_dict(cls, data: dict, index: int) -> "ObjectRoleBinding":
        prefix = f"object_role_bindings[{index}]"
        return cls(
            role_key=_validated_key(data.get("role_key"), f"{prefix}.role_key"),
            semantic_key=_validated_semantic_key(
                data.get("semantic_key"), f"{prefix}.semantic_key"
            ),
            object_label=_required_text(data, "object_label", f"{prefix}.object_label"),
        )


@dataclass(frozen=True)
class DeclaredBridge:
    semantic_key: str
    source_role_key: str
    predicate: str
    target_role_key: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "semantic_key",
            _validated_key(self.semantic_key, "semantic_key"),
        )
        object.__setattr__(
            self,
            "source_role_key",
            _validated_key(self.source_role_key, "source_role_key"),
        )
        object.__setattr__(
            self,
            "predicate",
            _validated_predicate(self.predicate, "predicate"),
        )
        object.__setattr__(
            self,
            "target_role_key",
            _validated_key(self.target_role_key, "target_role_key"),
        )

    @classmethod
    def from_dict(cls, data: dict, index: int) -> "DeclaredBridge":
        prefix = f"declared_bridges[{index}]"
        return cls(
            semantic_key=_validated_key(
                data.get("semantic_key"), f"{prefix}.semantic_key"
            ),
            source_role_key=_validated_key(
                data.get("source_role_key"), f"{prefix}.source_role_key"
            ),
            predicate=_validated_predicate(
                data.get("predicate"), f"{prefix}.predicate"
            ),
            target_role_key=_validated_key(
                data.get("target_role_key"), f"{prefix}.target_role_key"
            ),
        )


@dataclass(frozen=True)
class ReadinessDeclaration:
    requirement_key: str
    status: ReadinessStatus

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement_key",
            _validated_key(self.requirement_key, "requirement_key"),
        )
        if not isinstance(self.status, ReadinessStatus):
            raise ScenarioValidationError(
                "status must be ready, to_confirm, or unavailable"
            )

    @classmethod
    def from_dict(cls, data: dict, index: int) -> "ReadinessDeclaration":
        prefix = f"readiness_declarations[{index}]"
        try:
            status = ReadinessStatus(data.get("status"))
        except (TypeError, ValueError) as error:
            raise ScenarioValidationError(
                f"{prefix}.status must be ready, to_confirm, or unavailable"
            ) from error
        return cls(
            requirement_key=_validated_key(
                data.get("requirement_key"), f"{prefix}.requirement_key"
            ),
            status=status,
        )


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


def _validated_object_role_bindings(
    value: object,
) -> tuple[ObjectRoleBinding, ...]:
    if not isinstance(value, tuple):
        raise ScenarioValidationError("object_role_bindings must be a tuple")
    if any(not isinstance(item, ObjectRoleBinding) for item in value):
        raise ScenarioValidationError(
            "object_role_bindings must be a tuple of ObjectRoleBinding"
        )
    return value


def _validated_declared_bridges(value: object) -> tuple[DeclaredBridge, ...]:
    if not isinstance(value, tuple):
        raise ScenarioValidationError("declared_bridges must be a tuple")
    if any(not isinstance(item, DeclaredBridge) for item in value):
        raise ScenarioValidationError(
            "declared_bridges must be a tuple of DeclaredBridge"
        )
    return value


def _validated_readiness_declarations(
    value: object,
) -> tuple[ReadinessDeclaration, ...]:
    if not isinstance(value, tuple):
        raise ScenarioValidationError("readiness_declarations must be a tuple")
    if any(not isinstance(item, ReadinessDeclaration) for item in value):
        raise ScenarioValidationError(
            "readiness_declarations must be a tuple of ReadinessDeclaration"
        )
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
    decision_key: str = ""
    object_role_bindings: tuple[ObjectRoleBinding, ...] = ()
    declared_bridges: tuple[DeclaredBridge, ...] = ()
    readiness_declarations: tuple[ReadinessDeclaration, ...] = ()

    def __post_init__(self) -> None:
        for field, minimum_items in (
            ("objects", 2),
            ("acceptance_questions", 1),
            ("participants", 0),
            ("constraints", 0),
            ("desired_actions", 0),
        ):
            object.__setattr__(
                self,
                field,
                _validated_string_tuple(
                    getattr(self, field), field, minimum_items=minimum_items
                ),
            )
        object.__setattr__(
            self,
            "decision_key",
            _validated_key(self.decision_key, "decision_key", optional=True),
        )
        object.__setattr__(
            self,
            "data_sources",
            _validated_data_sources(self.data_sources),
        )
        object.__setattr__(self, "relations", _validated_relations(self.relations))
        object.__setattr__(
            self,
            "object_role_bindings",
            _validated_object_role_bindings(self.object_role_bindings),
        )
        object.__setattr__(
            self,
            "declared_bridges",
            _validated_declared_bridges(self.declared_bridges),
        )
        object.__setattr__(
            self,
            "readiness_declarations",
            _validated_readiness_declarations(self.readiness_declarations),
        )
        for index, relation in enumerate(self.relations):
            if relation.source not in self.objects:
                raise ScenarioValidationError(
                    f"relations[{index}].source must reference an object"
                )
            if relation.target not in self.objects:
                raise ScenarioValidationError(
                    f"relations[{index}].target must reference an object"
                )
        role_keys = tuple(item.role_key for item in self.object_role_bindings)
        if len(set(role_keys)) != len(role_keys):
            raise ScenarioValidationError("duplicate object role")
        for index, binding in enumerate(self.object_role_bindings):
            if binding.object_label not in self.objects:
                raise ScenarioValidationError(
                    f"object_role_bindings[{index}].object_label must reference an object"
                )
        known_roles = set(role_keys)
        bridge_keys = tuple(item.semantic_key for item in self.declared_bridges)
        if len(set(bridge_keys)) != len(bridge_keys):
            raise ScenarioValidationError("duplicate declared bridge")
        for index, bridge in enumerate(self.declared_bridges):
            if (
                bridge.source_role_key not in known_roles
                or bridge.target_role_key not in known_roles
            ):
                raise ScenarioValidationError(
                    f"declared_bridges[{index}] references unknown role"
                )
        readiness_keys = tuple(
            item.requirement_key for item in self.readiness_declarations
        )
        if len(set(readiness_keys)) != len(readiness_keys):
            raise ScenarioValidationError("duplicate readiness declaration")
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
        structured_fields = (
            ("object_role_bindings", ObjectRoleBinding),
            ("declared_bridges", DeclaredBridge),
            ("readiness_declarations", ReadinessDeclaration),
        )
        for field, _ in structured_fields:
            raw = data.get(field, [])
            if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
                raise ScenarioValidationError(f"{field} must be a list of objects")
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
            decision_key=_validated_key(
                data.get("decision_key", ""), "decision_key", optional=True
            ),
            object_role_bindings=tuple(
                ObjectRoleBinding.from_dict(item, index)
                for index, item in enumerate(data.get("object_role_bindings", []))
            ),
            declared_bridges=tuple(
                DeclaredBridge.from_dict(item, index)
                for index, item in enumerate(data.get("declared_bridges", []))
            ),
            readiness_declarations=tuple(
                ReadinessDeclaration.from_dict(item, index)
                for index, item in enumerate(data.get("readiness_declarations", []))
            ),
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
    input_bindings: tuple[InputBinding, ...] = ()
    knowledge_source_refs: tuple[SourceRef, ...] = ()
    knowledge_outcomes: tuple[KnowledgeOutcome, ...] = ()

    def __post_init__(self) -> None:
        from ontology_poc_generator.decision_pack import InputBinding
        from ontology_poc_generator.knowledge import KnowledgeOutcome, SourceRef

        for field, item_type in (
            ("input_bindings", InputBinding),
            ("knowledge_source_refs", SourceRef),
            ("knowledge_outcomes", KnowledgeOutcome),
        ):
            value = getattr(self, field)
            if not isinstance(value, tuple) or any(
                not isinstance(item, item_type) for item in value
            ):
                raise ScenarioValidationError(
                    f"{field} must be a tuple of {item_type.__name__}"
                )
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

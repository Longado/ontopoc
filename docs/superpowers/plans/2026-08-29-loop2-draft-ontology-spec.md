# Loop 2 — Draft OntologySpec Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Loop 1 的不可变 `DecisionPack` 无损编译为引用闭合、字节稳定、显式保留 `candidate / draft / synthetic_demo` 边界的本地 `OntologySpec`，并让所有尚不能机器化的建议以结构化 `CompilationIssue` 留在产物中。

**Architecture:** `DecisionPack` 仍是输入事实、来源和建议的权威对象；Loop 2 新增纯函数 `compile_ontology_spec(pack)`，把显式语义角色、桥接关系和已识别的 `payload_schema` 投影为 T-Box/规则声明。编译结果携带规范化 spec JSON、由 Loop 2 独占生成的 spec content hash 和引用闭包报告；编译器不得升级治理状态，也不得把 narrative、readiness gap 或未知 profile 静默丢弃。

**Tech Stack:** Python 3.11+ 标准库、frozen dataclasses、Enum、JSON、SHA-256、pathlib、unittest；无数据库、网络、LLM、RDF/OWL/SHACL 或旧 EIP 运行时依赖。

---

## 1. 进入条件与当前证据

本计划按 Loop 1 已接受的以下本地契约编写：

- `KnowledgeSuggestion` 已保留 `payload_schema`、不可变 payload、稳定 `suggestion_id`、输入 binding 和 source provenance；
- 已支持并校验 `relation_semantics.v1`、`constraint.narrative.v1`、`data_requirement.narrative.v1`、`acceptance_question.v1`、`readiness_gap.v1`；
- 稳定 binding/suggestion identity 不使用标签、数组位置、时间或随机数；
- 供应链知识单元的 queue policy 目前是 `readiness_gap`，不是规则；
- Loop 1 ADR 已明确：`DecisionPack` 不引入额外的 `OntologyCandidate` 层，Loop 2 必须“编译已识别 profile，或生成结构化 issue”，不得忽略 suggestion。

Loop 1 已完成 whole-loop review 并合并主分支。Loop 2 以主分支提交 `4e410c2` 为基线启动，基线全量测试为 **107 tests, OK**；当前在独立 worktree 分支 `codex/loop-2-draft-ontology-spec` 执行。Task 1 已在提交 `36a0e12` 冻结基础 spec 合同，聚焦测试 **14 passed**、全量测试 **121 passed**，规格审查和质量审查均通过；Task 2 正在隔离分支实现稳定 identity 与 canonical hash。此状态不表示编译、引用闭包或规则能力已经完成。

```text
in_progress
task_1_complete
task_2_in_progress
```

执行前必须先确认：

```bash
git log -1 --oneline
PYTHONPATH=src python -m unittest discover -s tests -v
git status --short
```

预期：Loop 1 已被独立审查标为完成；全量测试通过；除明确保留的用户文件外，工作树无未知改动。若最终 `DecisionPack` 字段名与本计划不一致，先只修订本计划的接口，不在实现里加兼容猜测。

### 1.1 加速执行与最小集成门

Loop 2 后续采用隔离分支并行、Loop 分支集成、主分支统一合并：

```text
Task 2 identity/hash
  -> Wave A: provided-input compiler
  -> Wave B: knowledge profile compiler
  -> Wave C: reference closure/result invariants
  -> Loop branch integration + one end-to-end review
  -> main
```

每个任务分支只保留四项必需门槛：

1. 与该任务行为直接对应的聚焦测试；
2. 一次全量 `unittest` 回归；
3. `git diff --check`；
4. 文件范围和工作树状态检查。

以下检查不再作为每个小提交的重复门槛：

- 同一提交重复运行 `pytest` 与 `unittest`；
- 每个 Task 都做规格审查和质量审查两轮；
- 每个 Task 都更新 ROADMAP、DISCOVERY 和完成证据；
- 为远期数据库、API、前端或客户数据路径提前做验收；
- 对当前严格 loader 不可能产生的未知 profile 重复设防。

每个并行实现提交只做一次独立代码审查；只有出现 P1/P2 或跨分支合同冲突时才追加复审。ROADMAP 与发现记录在 Loop 分支整合后统一更新。Task 8 的 synthetic policy 是 Loop 3 的进入门，不阻塞 Loop 2 基础编译出口，可在基础出口稳定后独立并行。

## 2. 产品问题与出口

Loop 2 只回答：

> 一个带来源的 candidate `DecisionPack`，能否变成机器可检查且没有语义丢失的 draft `OntologySpec`？

### 2.1 基础出口条件

以下条件全部满足，才算完成 Loop 2 的基础出口：

1. 同一 `DecisionPack` 重复编译得到完全相同的 canonical spec bytes 与 spec content hash。
2. `OntologySpec` 显式包含 `schema=ontology_spec.v1`、`stage=draft`、`evidence_scope=synthetic_demo`、`governance_status=candidate` 和输入 `pack_content_hash`。
3. `provided_input` 生成的类型和关系仍是 `candidate`；“用户提供”不等于“已确认”。
4. 每个 relation 都有显式 `domain_type_id` 与 `range_type_id`；两者必须引用 spec 内已声明 entity type。
5. `relation_semantics.v1` 能确定性编译为 relation type；角色标签变化不改变 entity/relation ID。
6. `constraint.narrative.v1`、`data_requirement.narrative.v1`、`acceptance_question.v1`、`readiness_gap.v1` 各自产生绑定原 `suggestion_id` 的 `CompilationIssue`。
7. queue policy readiness gap 只能产生 issue，不能自动生成 rule。
8. 每条 applicable suggestion 必须被且只被以下一种方式承接：编译为 spec element，或记录为 `CompilationIssue`。
9. 引用闭包报告为 `is_closed=true`；手工构造的 dangling domain/range、binding、suggestion 或 rule input 会产生稳定 issue 并使闭包失败。
10. canonical spec hash 只由 Loop 2 生成；Loop 2 不重算或接管 pack hash。
11. `SpecCompilationResult.compilation_status=complete`，且 spec 内 `blocking` severity 的 compilation issues 数量为零。

### 2.2 进入 Loop 3 的额外 gate

基础出口允许 `rule_declarations=()`，但这不允许进入 Loop 3。进入 Loop 3 前还必须有一份独立审查通过的 `decision_rule.v1` synthetic policy slice，并满足：

- 明确标记 `evidence_scope=synthetic_demo`；
- 来源只能证明“这是测试用政策设计”，不得写成客户事实、行业事实或最终产品阈值；
- profile 明确声明 rule kind、subject role、输入 semantic keys 和输出 conclusion key；
- 不把当前 `queue_entry_evidence_policy` readiness gap 自动提升为规则；
- 不出现未经独立 policy-design 评审接受的数值阈值、评分权重或处置动作；
- 能编译为引用闭合的 `RuleDeclarationSpec`，并由 Loop 3 明确支持其 `rule_kind`。
- 编译结果仍为 `compilation_status=complete`，且没有 blocking compilation issue。

该 gate 与基础 `OntologySpec + hash + closure report` 分开提交、分开审查。若 policy-design 结论尚未冻结，完成基础出口后停止；不要用临时阈值解除 Loop 3 阻塞。

## 3. 非目标

- 不加载事实，不做 T-Box 实例校验，不求值规则，不生成 `ValidationReceipt`。
- 不生成订单入队/不入队结论、风险分数、供应商选择或干预动作。
- 不引入 pack version/base、review、publication、semantic diff 或 `DecisionDelta`。
- 不做数据映射、row lineage、数据库持久化、API、前端或外部 writeback。
- 不复制旧 EIP 的 ORM、migration、router、service 或 UI。
- 不把 `provided_input`、`implemented_artifact`、`practitioner_note` 或 `synthetic_example` 当成 `confirmed`。
- 不把自然语言 description 解析成表达式；自然语言只能进入 display 字段或 `CompilationIssue`。
- 不在本轮增加通用规则 DSL、推理机、RDF、OWL、SHACL、SPARQL、Ontop 或 TypeDB。

## 4. 文件结构与职责

基础出口只引入以下文件：

```text
src/ontology_poc_generator/
├── ontology_spec.py       frozen spec dataclasses、canonical JSON、spec hash
├── spec_compiler.py       DecisionPack -> OntologySpec 的纯编译器与 profile dispatch
├── validation.py          spec 引用闭包检查；不做事实/规则求值
├── identity.py            增加 entity/relation/rule/issue 稳定 ID helper
└── errors.py              OntologySpecValidationError / SpecCompilationError

tests/
├── test_ontology_spec.py  spec 合同、状态、canonical bytes/hash
├── test_spec_compiler.py  provided input、profile 编译、issue accounting
└── test_validation.py     domain/range/binding/suggestion/rule 引用闭包
```

仅在 synthetic rule gate 获得独立 policy-design 结论后，才增加：

```text
knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json
knowledge/supply_chain/sources/order_priority_policy_synthetic_s1_v1.md
tests/fixtures/knowledge/order_priority_policy_synthetic_candidate_v2.json
tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json
tests/test_synthetic_policy_unit.py
```

CLI JSON 投影只在基础领域合同通过后增加，避免把 renderer 与 contract commit 混在一起。

## 5. 冻结合同

### 5.1 状态枚举

Loop 2 使用严格枚举，不接受自由文本状态：

```python
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
```

本轮没有 `confirmed`、`published` 或 `verified` 枚举值，从类型层阻止编译器越权升级。

### 5.2 Spec dataclasses

```python
@dataclass(frozen=True)
class EntityTypeSpec:
    type_id: str
    role_key: str
    semantic_key: str
    label: str
    governance_status: SpecGovernanceStatus
    origin_kind: SpecOriginKind
    origin_ref_id: str


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


@dataclass(frozen=True)
class PropertyTypeSpec:
    property_type_id: str
    semantic_key: str
    domain_type_id: str
    value_type: str
    governance_status: SpecGovernanceStatus
    origin_kind: SpecOriginKind
    origin_ref_id: str


@dataclass(frozen=True)
class RuleConditionSpec:
    property_type_id: str
    operator: str
    allowed_values: tuple[str, ...]


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


@dataclass(frozen=True)
class CompilationIssue:
    issue_id: str
    code: str
    severity: CompilationIssueSeverity
    suggestion_id: str
    payload_schema: str
    message: str


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
```

约束：

- 所有 tuple 在构造时按稳定 ID 排序；重复 ID 立即拒绝。
- `origin_ref_id` 对 `provided_input` entity 使用 binding ID，对 `provided_input` relation 使用 declared bridge semantic key，对知识元素使用 suggestion ID。
- `description` 与 `label` 可进入 spec 内容和 hash，但不进入 element identity seed。
- `PropertyTypeSpec` 和 `RuleDeclarationSpec` 在基础出口可以为空；只有 `decision_rule.v1` gate 通过后才产生实例。rule profile 明确生成其 symbolic-state property types，编译器不得从 narrative 猜 property。
- `CompilationIssue` 属于 spec 内容，因而被 spec hash 覆盖；不能在 hash 之外维护一份可能漂移的 issue sidecar。

### 5.3 Closure contract

```python
@dataclass(frozen=True)
class ClosureIssue:
    issue_id: str
    code: str
    owner_id: str
    field: str
    referenced_id: str


@dataclass(frozen=True)
class ReferenceClosureReport:
    is_closed: bool
    checked_reference_count: int
    issues: tuple[ClosureIssue, ...]


@dataclass(frozen=True)
class SpecCompilationResult:
    spec: OntologySpec
    spec_content_hash: str
    closure_report: ReferenceClosureReport
    compilation_status: CompilationStatus
```

`compilation_status` 是由 `spec.compilation_issues` 派生的 envelope 状态：存在任一 `blocking` issue 时为 `blocked`，否则为 `complete`。它不进入 `OntologySpec`，因此不进入 spec content hash；测试必须证明相同 spec 的派生状态不需要第二份持久化来源。

闭包必须检查：

- relation `domain_type_id` / `range_type_id` -> entity type；
- property `domain_type_id` -> entity type；
- entity `origin_ref_id` -> pack input binding（当 origin 是 `provided_input`）；
- provided-input relation `origin_ref_id` -> `pack.scenario.declared_bridges[*].semantic_key`；这是 bridge 对已被 `pack_content_hash` 覆盖的 pack 内容引用，不是 `SourceRef`；
- knowledge element/issue `origin_ref_id` 或 `suggestion_id` -> pack applicable suggestion；
- rule `subject_type_id` -> entity type；
- rule condition `property_type_id` -> property type；
- 每个 applicable suggestion 恰好落到 element 或 issue；
- 同一 suggestion 不得同时被 element 和 issue 消费，除非未来新 ADR 明确允许；本轮不允许。

### 5.4 Hash ownership

```text
Loop 1: canonical DecisionPack bytes -> pack_content_hash
Loop 2: canonical OntologySpec bytes -> spec_content_hash
Loop 3: canonical facts/receipt bytes -> facts/receipt content hash
Loop 4: version/base/review/delta/publication lifecycle identity
```

`compile_ontology_spec(pack)` 调用 Loop 1 已接受的 `decision_pack_content_hash(pack)` 得到输入 hash；Loop 2 不复制或重写 pack hash 算法。`spec_content_hash` 不存回 `OntologySpec`，避免自引用；它由 `ontology_spec_content_hash(spec)` 返回并放在 `SpecCompilationResult`。

规范化 JSON：

```python
json.dumps(
    ontology_spec_to_dict(spec),
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
)
```

编码固定为 UTF-8，SHA-256 输出小写 64 位 hex。

## 6. Profile 编译矩阵

| `payload_schema` | Loop 2 行为 | `CompilationIssue.code` | 是否生成 rule |
|---|---|---|---|
| `relation_semantics.v1` | 解析 source/target role，生成显式 domain/range relation type | 无 | 否 |
| `constraint.narrative.v1` | 保留 suggestion，不解析自然语言 | `narrative_constraint_requires_formalization` | 否 |
| `data_requirement.narrative.v1` | 保留为待数据设计问题 | `data_requirement_not_executable` | 否 |
| `acceptance_question.v1` | 保留为验收输入，不冒充规则 | `acceptance_question_not_executable` | 否 |
| `readiness_gap.v1` | 保留缺口，阻止错误的 rule promotion | `readiness_gap_blocks_rule_compilation` | 否 |
| `decision_rule.v1` | Task 8 与严格 loader profile 同一提交启用，并编译为 property + rule declarations | rule kind 未支持时为 `unsupported_rule_kind` | 是 |

所有能进入 `DecisionPack` 的 profile 先由 Loop 1 严格 loader 校验，未知 `payload_schema` 在 pack 构造前即被拒绝，因此 Loop 2 不保留不可达的 unknown-profile 分支。所有可达 issue 都绑定原始 `suggestion_id` 和 `payload_schema`；issue message 只做可读说明，不承载机器分支，机器判断使用 `code` 和 `severity`。

## 7. Task 1 — 冻结 spec 类型与状态边界

**执行状态：in_progress**

当前仅开始按测试驱动方式冻结合同；本节所有验收步骤仍以实际实现、测试与独立审查结果为准。

**Files:**

- Create: `src/ontology_poc_generator/ontology_spec.py`
- Modify: `src/ontology_poc_generator/errors.py`
- Create: `tests/test_ontology_spec.py`

- [ ] **Step 1: 写失败的导入与冻结测试**

```python
from dataclasses import FrozenInstanceError
import unittest

from ontology_poc_generator.ontology_spec import (
    CompilationIssue,
    CompilationIssueSeverity,
    CompilationStatus,
    EntityTypeSpec,
    EvidenceScope,
    OntologySpec,
    RelationTypeSpec,
    SpecGovernanceStatus,
    SpecOriginKind,
    SpecStage,
)


class OntologySpecContractTest(unittest.TestCase):
    def test_spec_is_frozen_candidate_draft_synthetic(self):
        spec = OntologySpec(
            schema="ontology_spec.v1",
            decision_key="order_priority_intervention",
            pack_content_hash="a" * 64,
            stage=SpecStage.DRAFT,
            evidence_scope=EvidenceScope.SYNTHETIC_DEMO,
            governance_status=SpecGovernanceStatus.CANDIDATE,
            input_binding_ids=(),
            entity_types=(),
            relation_types=(),
            property_types=(),
            rule_declarations=(),
            compilation_issues=(),
        )
        with self.assertRaises(FrozenInstanceError):
            spec.stage = "published"
```

- [ ] **Step 2: 运行并确认失败原因**

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_ontology_spec -v
```

Expected: FAIL，原因是 `ontology_spec` 模块或合同尚不存在。

- [ ] **Step 3: 实现第 5.1–5.2 节的 frozen dataclasses 和严格校验**

校验必须拒绝：空 ID、非 SHA-256 pack hash、非 tuple 集合、重复 element/issue ID、非 candidate 状态、非 draft stage、非 `synthetic_demo` scope。不要增加 confirmed/published 状态。

`errors.py` 同时增加带稳定机器 code 的 fatal error；它用于“输入 pack 已破坏编译合同、无法形成可信 spec”，不进入 `OntologySpec.compilation_issues`：

```python
class SpecCompilationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
```

- [ ] **Step 4: 添加并通过负向测试**

```python
def test_rejects_duplicate_relation_type_ids(self):
    relation = relation_fixture(relation_type_id="relation_same")
    with self.assertRaisesRegex(
        OntologySpecValidationError, "duplicate relation_type_id"
    ):
        spec_fixture(relation_types=(relation, relation))


def test_enum_has_no_confirmed_or_published_value(self):
    with self.assertRaises(ValueError):
        SpecGovernanceStatus("confirmed")
    with self.assertRaises(ValueError):
        SpecStage("published")
```

Run:

```bash
PYTHONPATH=src python -m unittest tests.test_ontology_spec -v
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
```

- [ ] **Step 5: 小提交**

```bash
git add src/ontology_poc_generator/ontology_spec.py \
  src/ontology_poc_generator/errors.py tests/test_ontology_spec.py
git commit -m "feat: define draft ontology spec contracts"
```

## 8. Task 2 — 增加稳定 element identity 与 canonical spec hash

**Files:**

- Modify: `src/ontology_poc_generator/identity.py`
- Modify: `src/ontology_poc_generator/ontology_spec.py`
- Modify: `tests/test_identity.py`
- Modify: `tests/test_ontology_spec.py`

- [ ] **Step 1: 写 identity 失败测试**

```python
def test_spec_ids_ignore_display_labels(self):
    entity_a = stable_entity_type_id(
        "order_priority_intervention", "supplier", "supplier.candidate"
    )
    entity_b = stable_entity_type_id(
        "order_priority_intervention", "supplier", "supplier.candidate"
    )
    self.assertEqual(entity_a, entity_b)

    relation_a = stable_relation_type_id(
        "supplier_qualified_to_supply_material",
        entity_a,
        "QUALIFIED_TO_SUPPLY",
        "type_material",
    )
    relation_b = stable_relation_type_id(
        "supplier_qualified_to_supply_material",
        entity_b,
        "QUALIFIED_TO_SUPPLY",
        "type_material",
    )
    self.assertEqual(relation_a, relation_b)
```

ID helper 精确签名：

```python
stable_entity_type_id(decision_key, role_key, semantic_key) -> str
stable_relation_type_id(semantic_key, domain_type_id, predicate, range_type_id) -> str
stable_property_type_id(semantic_key, domain_type_id) -> str
stable_rule_id(semantic_key, rule_kind, subject_type_id, output_conclusion_key) -> str
stable_compilation_issue_id(suggestion_id, code, payload_schema) -> str
```

- [ ] **Step 2: 运行并确认 helper 缺失**

```bash
PYTHONPATH=src python -m unittest tests.test_identity -v
```

- [ ] **Step 3: 复用现有 `_stable_id`，实现五个 helper**

保持现有 binding/suggestion ID 不变；不要重命名或批量重构 `identity.py`。

- [ ] **Step 4: 写 canonical bytes/hash 失败测试**

```python
def test_canonical_hash_is_repeatable_and_order_independent(self):
    first = spec_fixture(entity_types=(supplier_entity(), material_entity()))
    second = spec_fixture(entity_types=(material_entity(), supplier_entity()))
    self.assertEqual(
        canonical_ontology_spec_json(first),
        canonical_ontology_spec_json(second),
    )
    self.assertEqual(
        ontology_spec_content_hash(first),
        ontology_spec_content_hash(second),
    )
```

- [ ] **Step 5: 实现 `ontology_spec_to_dict`、canonical JSON 与 SHA-256**

所有 element 和 issue 按稳定 ID 排序后序列化；Enum 写 value；tuple 写 JSON array；不得把 spec hash 写入被 hash 的对象。

- [ ] **Step 6: 运行、检查、提交**

```bash
PYTHONPATH=src python -m unittest tests.test_identity tests.test_ontology_spec -v
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
git add src/ontology_poc_generator/identity.py \
  src/ontology_poc_generator/ontology_spec.py \
  tests/test_identity.py tests/test_ontology_spec.py
git commit -m "feat: add stable ontology spec identity"
```

## 9. Task 3 — 编译 provided input 为 candidate entity/relation types

**Files:**

- Create: `src/ontology_poc_generator/spec_compiler.py`
- Create: `tests/test_spec_compiler.py`

- [ ] **Step 1: 写黄金 pack 的 provided-input 失败测试**

```python
def test_compiles_provided_input_as_candidate_draft_types(self):
    pack = compile_golden_pack()
    result = compile_ontology_spec(pack)

    self.assertEqual(result.spec.stage, SpecStage.DRAFT)
    self.assertEqual(result.spec.evidence_scope, EvidenceScope.SYNTHETIC_DEMO)
    self.assertEqual(
        result.spec.governance_status, SpecGovernanceStatus.CANDIDATE
    )
    self.assertTrue(result.spec.entity_types)
    self.assertTrue(result.spec.relation_types)
    self.assertTrue(all(
        item.governance_status is SpecGovernanceStatus.CANDIDATE
        for item in result.spec.entity_types + result.spec.relation_types
    ))
```

- [ ] **Step 2: 写 domain/range 显式性测试**

```python
def test_declared_bridge_has_explicit_domain_and_range(self):
    result = compile_ontology_spec(compile_golden_pack())
    relation = next(
        item for item in result.spec.relation_types
        if item.semantic_key == "customer_order_requires_material"
    )
    entity_ids = {item.type_id for item in result.spec.entity_types}
    self.assertIn(relation.domain_type_id, entity_ids)
    self.assertIn(relation.range_type_id, entity_ids)
    self.assertEqual(relation.origin_kind, SpecOriginKind.PROVIDED_INPUT)
```

- [ ] **Step 3: 运行并确认编译器缺失**

```bash
PYTHONPATH=src python -m unittest tests.test_spec_compiler -v
```

- [ ] **Step 4: 实现最小 `compile_ontology_spec(pack)` 骨架**

第一步只编译：

```text
pack.scenario.object_role_bindings -> EntityTypeSpec
pack.scenario.declared_bridges -> RelationTypeSpec
```

所有产物固定 `candidate/draft/synthetic_demo`。编译器使用 binding 的 role/semantic key 建 ID，使用 label 只做 display；不得读取 `industry` 或自然语言 `business_decision` 推断类型/关系。

- [ ] **Step 5: 添加 rename/reorder 回归**

```python
def test_label_rename_and_object_reorder_keep_element_ids(self):
    first = compile_ontology_spec(compile_golden_pack())
    second = compile_ontology_spec(compile_renamed_reordered_pack())
    self.assertEqual(
        {item.type_id for item in first.spec.entity_types},
        {item.type_id for item in second.spec.entity_types},
    )
    self.assertEqual(
        {item.relation_type_id for item in first.spec.relation_types},
        {item.relation_type_id for item in second.spec.relation_types},
    )
```

- [ ] **Step 6: 运行、检查、提交**

```bash
PYTHONPATH=src python -m unittest tests.test_spec_compiler -v
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
git add src/ontology_poc_generator/spec_compiler.py tests/test_spec_compiler.py
git commit -m "feat: compile candidate ontology types"
```

## 10. Task 4 — 编译 `relation_semantics.v1`

**Files:**

- Modify: `src/ontology_poc_generator/spec_compiler.py`
- Modify: `tests/test_spec_compiler.py`

- [ ] **Step 1: 写 relation profile 失败测试**

```python
def test_relation_semantics_compiles_with_explicit_domain_range(self):
    result = compile_ontology_spec(compile_golden_pack())
    qualified = next(
        item for item in result.spec.relation_types
        if item.predicate == "QUALIFIED_TO_SUPPLY"
    )
    entities = {item.type_id: item for item in result.spec.entity_types}
    self.assertEqual(entities[qualified.domain_type_id].role_key, "supplier")
    self.assertEqual(entities[qualified.range_type_id].role_key, "material")
    self.assertEqual(
        qualified.origin_kind, SpecOriginKind.KNOWLEDGE_SUGGESTION
    )
    self.assertTrue(qualified.origin_ref_id.startswith("suggestion_"))
```

- [ ] **Step 2: 写禁止用显示标签做 domain/range 的测试**

```python
def test_relation_endpoints_are_type_ids_not_labels(self):
    result = compile_ontology_spec(compile_golden_pack())
    for relation in result.spec.relation_types:
        self.assertNotIn(relation.domain_type_id, {"供应商", "物料", "客户订单"})
        self.assertNotIn(relation.range_type_id, {"供应商", "物料", "客户订单"})
```

- [ ] **Step 3: 实现显式 profile dispatch**

使用精确分支：

```python
if suggestion.payload_schema == "relation_semantics.v1":
    return _compile_relation_semantics(suggestion, bindings_by_id, types_by_binding_id)
```

`_compile_relation_semantics` 只读取 profile 已校验的 `source_role_key`、`predicate`、`target_role_key`、`description`；若角色无法解析到 pack binding，抛 `SpecCompilationError(code="missing_relation_role_binding", ...)`，不得猜测、降级到 label match 或把结构损坏包装成 `CompilationIssue`。

先写精确负测：

```python
def test_missing_relation_role_binding_is_a_typed_compilation_error(self):
    with self.assertRaises(SpecCompilationError) as caught:
        compile_ontology_spec(pack_with_broken_relation_role())
    self.assertEqual(caught.exception.code, "missing_relation_role_binding")
```

- [ ] **Step 4: 添加 supplied/history distinction 回归**

确认 `QUALIFIED_TO_SUPPLY` 与 `HAS_SUPPLIED` 是两个不同 relation type，且没有输出 `SUPPLIES`。

- [ ] **Step 5: 运行、检查、提交**

```bash
PYTHONPATH=src python -m unittest tests.test_spec_compiler -v
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
git add src/ontology_poc_generator/spec_compiler.py tests/test_spec_compiler.py
git commit -m "feat: compile relation semantics profile"
```

## 11. Task 5 — 对 narrative 和 readiness 建立无损 `CompilationIssue`

**Files:**

- Modify: `src/ontology_poc_generator/spec_compiler.py`
- Modify: `tests/test_spec_compiler.py`

- [ ] **Step 1: 写每个非机器化 profile 的失败测试**

```python
def test_every_non_machine_profile_becomes_a_bound_issue(self):
    pack = compile_golden_pack()
    result = compile_ontology_spec(pack)
    issue_by_schema = {
        issue.payload_schema: issue for issue in result.spec.compilation_issues
    }
    self.assertEqual(
        set(issue_by_schema),
        {
            "constraint.narrative.v1",
            "data_requirement.narrative.v1",
            "acceptance_question.v1",
            "readiness_gap.v1",
        },
    )
    suggestion_ids = {
        suggestion.suggestion_id
        for outcome in pack.knowledge_outcomes
        for suggestion in outcome.suggestions
    }
    self.assertTrue(all(
        issue.suggestion_id in suggestion_ids
        for issue in result.spec.compilation_issues
    ))
```

若同一 schema 在 pack 中有多条 suggestion，按 suggestion 数量断言，不得用 dict 覆盖；测试 fixture 应覆盖两个 `data_requirement.narrative.v1`。

- [ ] **Step 2: 写 queue policy 不升格测试**

```python
def test_queue_readiness_gap_never_becomes_a_rule(self):
    result = compile_ontology_spec(compile_golden_pack())
    self.assertEqual(result.spec.rule_declarations, ())
    self.assertIn(
        "readiness_gap_blocks_rule_compilation",
        {issue.code for issue in result.spec.compilation_issues},
    )
```

- [ ] **Step 3: 实现 profile -> issue 显式映射**

```python
NON_EXECUTABLE_PROFILE_CODES = {
    "constraint.narrative.v1": "narrative_constraint_requires_formalization",
    "data_requirement.narrative.v1": "data_requirement_not_executable",
    "acceptance_question.v1": "acceptance_question_not_executable",
    "readiness_gap.v1": "readiness_gap_blocks_rule_compilation",
}
```

每个 issue 使用 `stable_compilation_issue_id`，上述四个严格 profile 的 severity 都是 `requires_review`。未知 profile 由 Loop 1 loader 在 pack 之前拒绝；这里不写不可达 fallback。不要解析 description 中的关键词。

- [ ] **Step 4: 写 suggestion accounting 失败测试**

```python
def test_every_applicable_suggestion_is_accounted_once(self):
    pack = compile_golden_pack()
    result = compile_ontology_spec(pack)
    expected = {
        suggestion.suggestion_id
        for outcome in pack.knowledge_outcomes
        for suggestion in outcome.suggestions
    }
    compiled = {
        relation.origin_ref_id
        for relation in result.spec.relation_types
        if relation.origin_kind is SpecOriginKind.KNOWLEDGE_SUGGESTION
    }
    issued = {issue.suggestion_id for issue in result.spec.compilation_issues}
    self.assertEqual(compiled | issued, expected)
    self.assertFalse(compiled & issued)
```

- [ ] **Step 5: 运行、检查、提交**

```bash
PYTHONPATH=src python -m unittest tests.test_spec_compiler -v
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
git add src/ontology_poc_generator/spec_compiler.py tests/test_spec_compiler.py
git commit -m "feat: preserve ontology compilation issues"
```

## 12. Task 6 — 建立引用闭包报告并让 dangling references 响亮失败

**Files:**

- Create: `src/ontology_poc_generator/validation.py`
- Create: `tests/test_validation.py`
- Modify: `src/ontology_poc_generator/spec_compiler.py`
- Modify: `src/ontology_poc_generator/ontology_spec.py`

- [ ] **Step 1: 写闭包成功测试**

```python
def test_golden_spec_has_closed_references(self):
    pack = compile_golden_pack()
    result = compile_ontology_spec(pack)
    self.assertTrue(result.closure_report.is_closed)
    self.assertEqual(result.closure_report.issues, ())
    self.assertGreater(result.closure_report.checked_reference_count, 0)
    self.assertEqual(result.compilation_status, CompilationStatus.COMPLETE)
    self.assertFalse(any(
        issue.severity is CompilationIssueSeverity.BLOCKING
        for issue in result.spec.compilation_issues
    ))
```

另加纯派生测试：给 spec fixture 加一个 blocking issue 后，envelope helper 返回 `CompilationStatus.BLOCKED`；删除该 issue 后返回 `COMPLETE`。状态不得写回 spec 或改变 spec hash 之外的内容。

- [ ] **Step 2: 写 dangling 引用失败测试**

```python
def test_reports_dangling_relation_domain(self):
    spec = spec_fixture(
        relation_types=(relation_fixture(domain_type_id="type_missing"),)
    )
    report = validate_reference_closure(spec, pack_fixture())
    self.assertFalse(report.is_closed)
    self.assertIn("dangling_relation_domain", {item.code for item in report.issues})


def test_reports_unknown_origin_suggestion(self):
    spec = spec_fixture(
        compilation_issues=(issue_fixture(suggestion_id="suggestion_missing"),)
    )
    report = validate_reference_closure(spec, pack_fixture())
    self.assertFalse(report.is_closed)
    self.assertIn("dangling_suggestion_reference", {item.code for item in report.issues})


def test_reports_unknown_provided_input_declared_bridge(self):
    spec = spec_fixture(
        relation_types=(provided_relation_fixture(origin_ref_id="bridge_missing"),)
    )
    report = validate_reference_closure(spec, pack_fixture())
    self.assertFalse(report.is_closed)
    self.assertIn("dangling_declared_bridge", {item.code for item in report.issues})
```

同文件再覆盖 `dangling_input_binding`、`dangling_property_domain` 与 `dangling_rule_property`。

- [ ] **Step 3: 实现纯函数 `validate_reference_closure(spec, pack)`**

报告中的 issue 按 `issue_id` 排序；`checked_reference_count` 只计实际检查过的引用边。函数不修复、不删除、不补猜引用。

- [ ] **Step 4: 让编译器返回完整 result，并拒绝内部闭包失败**

```python
spec = OntologySpec(...)
closure_report = validate_reference_closure(spec, pack)
if not closure_report.is_closed:
    raise SpecCompilationError(
        "compiled_spec_not_reference_closed",
        "compiled ontology spec is not reference-closed",
    )
return SpecCompilationResult(
    spec=spec,
    spec_content_hash=ontology_spec_content_hash(spec),
    closure_report=closure_report,
    compilation_status=(
        CompilationStatus.BLOCKED
        if any(
            issue.severity is CompilationIssueSeverity.BLOCKING
            for issue in spec.compilation_issues
        )
        else CompilationStatus.COMPLETE
    ),
)
```

用户手工调用 validator 可得到详细 report；编译器自己产生 dangling 引用则 fail loud，不能返回伪成功 result。

- [ ] **Step 5: 运行、检查、提交**

```bash
PYTHONPATH=src python -m unittest tests.test_validation tests.test_spec_compiler -v
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
git add src/ontology_poc_generator/validation.py \
  src/ontology_poc_generator/ontology_spec.py \
  src/ontology_poc_generator/spec_compiler.py \
  tests/test_validation.py tests/test_spec_compiler.py
git commit -m "feat: validate ontology reference closure"
```

## 13. Task 7 — 输出结构化 spec 证据并关闭基础出口

**Files:**

- Modify: `src/ontology_poc_generator/cli.py`
- Modify: `tests/test_cli.py`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/DISCOVERY_LOG.md`

- [ ] **Step 1: 写 opt-in CLI 失败测试**

在 Loop 1 已接受的 `--knowledge-unit` 参数基础上，新增 `--ontology-spec-output PATH`；未提供该参数时保持 Loop 1 输出完全不变。

```python
def test_cli_writes_draft_ontology_spec_envelope(self):
    result, output = run_cli_with_spec_output()
    self.assertEqual(result.returncode, 0, result.stderr)
    payload = json.loads(output.read_text(encoding="utf-8"))
    self.assertEqual(payload["spec"]["schema"], "ontology_spec.v1")
    self.assertEqual(payload["spec"]["stage"], "draft")
    self.assertEqual(payload["spec"]["evidence_scope"], "synthetic_demo")
    self.assertEqual(payload["spec"]["governance_status"], "candidate")
    self.assertRegex(payload["spec_content_hash"], r"^[0-9a-f]{64}$")
    self.assertTrue(payload["reference_closure"]["is_closed"])
    self.assertEqual(payload["compilation_status"], "complete")
    self.assertFalse(any(
        issue["severity"] == "blocking"
        for issue in payload["spec"]["compilation_issues"]
    ))
```

- [ ] **Step 2: 实现只负责 orchestration 的 CLI 路径**

CLI 调用现有 Loop 1 pack compiler，再调用 `compile_ontology_spec` 和 canonical projection；CLI 不创建 entity/relation/rule，不改变状态。spec envelope 固定包含：

```json
{
  "spec": {},
  "spec_content_hash": "64-char-lowercase-sha256",
  "compilation_status": "complete",
  "reference_closure": {
    "is_closed": true,
    "checked_reference_count": 1,
    "issues": []
  }
}
```

- [ ] **Step 3: 添加默认 CLI 兼容回归**

确认不带 `--ontology-spec-output` 时，Markdown/JSON bytes 与 Loop 1 已接受 golden 完全相同。

- [ ] **Step 4: 执行黄金场景 smoke**

```bash
loop2_tmp_dir="$(mktemp -d)"
PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/supply_chain_exception.json \
  --knowledge-unit knowledge/supply_chain/supplier_evidence_boundary_v1.json \
  --format json \
  --output "$loop2_tmp_dir/proposal.json" \
  --ontology-spec-output "$loop2_tmp_dir/ontology-spec.json"

python -m json.tool "$loop2_tmp_dir/ontology-spec.json" >/dev/null
```

人工检查：relation 有显式 domain/range；所有状态是 candidate/draft/synthetic_demo；narrative/readiness 都有 suggestion-bound issue；`compilation_status=complete` 且 blocking issue 为零；rule 为空；不存在 receipt/version/review/action/writeback。

- [ ] **Step 5: 更新真实证据并提交**

ROADMAP/DISCOVERY 只记录实际测试数、commit、hash/closure smoke 和已知 rule gate 阻塞；不得把“基础出口完成”写成“可执行验证已完成”。

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
git add src/ontology_poc_generator/cli.py tests/test_cli.py \
  docs/ROADMAP.md docs/DISCOVERY_LOG.md
git commit -m "docs: close draft ontology spec foundation"
```

## 14. Task 8 — 独立 synthetic `decision_rule.v1` gate

独立 policy-design 已接受一个最小、可证伪且没有数值阈值的 synthetic slice。它只用于验证编译和后续 delta 机制，不声称是客户政策：

```text
S-1 baseline:
supplier_commitment_state in [missed]
AND qualified_alternative_state in [none]
=> priority_intervention_queue_membership = in_queue

candidate revision:
supplier_commitment_state in [at_risk, missed]
AND qualified_alternative_state in [none]
=> priority_intervention_queue_membership = in_queue
```

两版使用相同 rule semantic key 和 stable rule ID；条件变化必须改变 spec hash。candidate revision 只作为后续 `DecisionDelta` 的受控 fixture，不在 Loop 2 发布或求值。

**Files:**

- Modify: `src/ontology_poc_generator/knowledge.py`
- Modify: `src/ontology_poc_generator/spec_compiler.py`
- Create: `knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json`
- Create: `knowledge/supply_chain/sources/order_priority_policy_synthetic_s1_v1.md`
- Create: `tests/fixtures/knowledge/order_priority_policy_synthetic_candidate_v2.json`
- Create: `tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json`
- Create: `tests/test_synthetic_policy_unit.py`
- Modify: `tests/test_spec_compiler.py`

`decision_rule.v1` profile 只允许以下字段：

```python
frozenset({
    "rule_kind",
    "subject_role_key",
    "condition_1_semantic_key",
    "condition_1_allowed_values",
    "condition_2_semantic_key",
    "condition_2_allowed_values",
    "output_conclusion_key",
    "positive_conclusion_value",
    "negative_conclusion_value",
    "description",
    "evidence_scope",
})
```

固定值与格式：

```text
rule_kind: categorical_all_of_v1
subject_role_key: customer_order
condition_1_semantic_key: supplier_commitment_state
condition_1_allowed_values: missed                  # candidate 为 at_risk,missed
condition_2_semantic_key: qualified_alternative_state
condition_2_allowed_values: none
output_conclusion_key: priority_intervention_queue_membership
positive_conclusion_value: in_queue
negative_conclusion_value: not_in_queue
evidence_scope: synthetic_demo
```

allowed values 是按字典序排列、逗号分隔的 controlled tokens；这不是自然语言 expression，也不允许比较符、数值阈值、权重或 Action。

policy cases fixture 固定四笔设计预期，供 Loop 3 的 dated plan 接管；Loop 2 只验证 fixture 可寻址和 snapshot，不执行它：

| subject | synthetic inputs | S-1 expected | candidate expected |
|---|---|---|---|
| `order.synthetic.001` | `missed` + `none` | `pass / in_queue` | `pass / in_queue` |
| `order.synthetic.002` | `at_risk` + `none` | `fail / not_in_queue` | `pass / in_queue`，即未来 `entered_queue` |
| `order.synthetic.003` | `on_track` + `available` | `fail / not_in_queue` | `fail / not_in_queue` |
| `order.synthetic.004` | `missed` + qualification input unavailable | `not_evaluable / information_insufficient` | `not_evaluable / information_insufficient` |

“qualification unavailable”必须在 Loop 3 表示为输入不可用/缺失状态，不能伪装成普通枚举值后计算为 `fail`。

- [ ] **Step 1: 写 profile 边界失败测试**

```python
def test_decision_rule_profile_requires_synthetic_demo_scope(self):
    data = accepted_policy_unit_dict()
    data["suggestion_templates"][0]["payload"]["evidence_scope"] = "customer"
    with self.assertRaisesRegex(
        KnowledgeValidationError,
        "decision_rule.v1 evidence_scope must be synthetic_demo",
    ):
        load_unit_from_dict(data)
```

同组测试拒绝 `threshold`、`expression`、`score`、`weight`、`action`、空 semantic key、未排序 allowed values 和非 token 值。

- [ ] **Step 2: 固定 synthetic source snapshot**

所有 policy source 的 `source_kind` 必须是 `synthetic_example`。source note 必须逐项写出：这是 synthetic test policy、不是客户事实、不是行业标准、不是生产阈值、没有 Action/score。fixture 内容完成后执行：

```bash
shasum -a 256 tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json
git hash-object tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json
```

把实际 SHA-256 和 git blob revision 写入 source note 与知识单元，并由测试重算核对；不得在计划阶段写入伪 hash。

- [ ] **Step 3: 写 baseline rule 编译失败测试**

```python
def test_s1_compiles_as_candidate_synthetic_rule_declaration(self):
    result = compile_ontology_spec(compile_pack_with_s1_policy_unit())
    self.assertEqual(len(result.spec.rule_declarations), 1)
    rule = result.spec.rule_declarations[0]
    self.assertEqual(rule.rule_kind, "categorical_all_of_v1")
    self.assertEqual(rule.governance_status, SpecGovernanceStatus.CANDIDATE)
    self.assertEqual(result.spec.evidence_scope, EvidenceScope.SYNTHETIC_DEMO)
    self.assertEqual(
        tuple(condition.allowed_values for condition in rule.conditions),
        (("missed",), ("none",)),
    )
    self.assertIn(rule.subject_type_id, {
        item.type_id for item in result.spec.entity_types
    })
    self.assertTrue(result.closure_report.is_closed)
```

- [ ] **Step 4: 写 candidate fixture 的 identity/hash 测试**

```python
def test_candidate_condition_change_keeps_rule_id_and_changes_spec_hash(self):
    baseline = compile_ontology_spec(compile_pack_with_s1_policy_unit())
    candidate = compile_ontology_spec(compile_pack_with_candidate_policy_fixture())
    self.assertEqual(
        baseline.spec.rule_declarations[0].rule_id,
        candidate.spec.rule_declarations[0].rule_id,
    )
    self.assertNotEqual(
        baseline.spec_content_hash,
        candidate.spec_content_hash,
    )
    self.assertEqual(
        candidate.spec.rule_declarations[0].conditions[0].allowed_values,
        ("at_risk", "missed"),
    )
```

- [ ] **Step 5: 实现 profile -> property/rule declarations**

`categorical_all_of_v1` 生成：

- 两个 `PropertyTypeSpec(value_type="symbolic_state")`，domain 都引用 `customer_order` entity type；
- 两个 `RuleConditionSpec(operator="in")`，allowed values 来自严格 token parser；
- 一个 candidate `RuleDeclarationSpec`。

编译器只映射 payload，不运行四笔 cases、不生成 conclusion。`queue_entry_evidence_policy` readiness-gap suggestion 继续产生 issue，与 rule suggestion 是两个独立来源和语义对象。

- [ ] **Step 6: 写 unsupported rule kind 负测**

```python
def test_unsupported_rule_kind_is_a_blocking_issue_not_a_rule(self):
    result = compile_ontology_spec(
        compile_pack_with_rule_kind("rolling_probability_v1")
    )
    self.assertEqual(result.spec.rule_declarations, ())
    self.assertIn(
        "unsupported_rule_kind",
        {issue.code for issue in result.spec.compilation_issues},
    )
    self.assertEqual(result.compilation_status, CompilationStatus.BLOCKED)
```

`rolling_probability_v1` 只存在于此负测，不进入产品知识包、能力清单或 roadmap 声明。

- [ ] **Step 7: 运行、检查、独立提交**

```bash
PYTHONPATH=src python -m unittest \
  tests.test_synthetic_policy_unit tests.test_spec_compiler -v
PYTHONPATH=src python -m unittest discover -s tests -v
git diff --check
git add src/ontology_poc_generator/knowledge.py \
  src/ontology_poc_generator/spec_compiler.py \
  knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json \
  knowledge/supply_chain/sources/order_priority_policy_synthetic_s1_v1.md \
  tests/fixtures/knowledge/order_priority_policy_synthetic_candidate_v2.json \
  tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json \
  tests/test_synthetic_policy_unit.py tests/test_spec_compiler.py
git commit -m "feat: add synthetic decision rule declaration"
```

- [ ] **Step 8: 独立审查 Loop 3 entry gate**

审查者必须明确回答：rule 是否仍是 `candidate/draft/synthetic_demo`；所有 source 是否为 `synthetic_example`；是否完全没有 Action/score/客户事实；baseline/candidate 是否同 ID 不同 hash；是否引用闭合；两份受支持编译结果是否都是 `compilation_status=complete` 且 blocking issue 为零；Loop 3 计划是否只支持 `categorical_all_of_v1` 并用四笔 fixture 产生精确四态。任何一项为否，Loop 3 继续 blocked。

## 15. 编译问题代码表

这些 code 在本轮冻结，测试直接断言，不依赖 message 文本：

```text
narrative_constraint_requires_formalization
data_requirement_not_executable
acceptance_question_not_executable
readiness_gap_blocks_rule_compilation
unsupported_rule_kind
duplicate_suggestion_consumption
unaccounted_suggestion
```

`SpecCompilationError.code`（fatal，不写入 spec，也不伪装成可继续 review 的 issue）：

```text
missing_relation_role_binding
compiled_spec_not_reference_closed
```

闭包报告 code：

```text
dangling_relation_domain
dangling_relation_range
dangling_declared_bridge
dangling_input_binding
dangling_suggestion_reference
dangling_property_domain
dangling_rule_subject_type
dangling_rule_property
```

## 16. 完整验证顺序

每个小提交先跑 focused tests，再跑全量。基础出口最终命令：

```bash
PYTHONPATH=src python -m unittest tests.test_ontology_spec -v
PYTHONPATH=src python -m unittest tests.test_identity -v
PYTHONPATH=src python -m unittest tests.test_spec_compiler -v
PYTHONPATH=src python -m unittest tests.test_validation -v
PYTHONPATH=src python -m unittest tests.test_cli -v
PYTHONPATH=src python -m unittest discover -s tests -v

loop2_verify_dir="$(mktemp -d)"
PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/supply_chain_exception.json \
  --knowledge-unit knowledge/supply_chain/supplier_evidence_boundary_v1.json \
  --format json \
  --output "$loop2_verify_dir/proposal.json" \
  --ontology-spec-output "$loop2_verify_dir/ontology-spec.json"

python -m json.tool "$loop2_verify_dir/ontology-spec.json" >/dev/null
git diff --check
git status --short
```

最终独立 reviewer 按第 2.1 节逐条核对。基础出口通过后，如果第 2.2/Task 8 gate 未通过，应报告：

```text
Loop 2 foundation complete
Loop 3 entry blocked by accepted synthetic decision_rule.v1 policy slice
```

不得把结构闭包、hash 稳定或 rule declaration 的存在写成规则已执行、业务结论已验证或客户政策已确认。

## 17. 建议提交序列

```text
feat: define draft ontology spec contracts
feat: add stable ontology spec identity
feat: compile candidate ontology types
feat: compile relation semantics profile
feat: preserve ontology compilation issues
feat: validate ontology reference closure
docs: close draft ontology spec foundation
feat: add synthetic decision rule declaration   # 仅在独立 gate 通过后
```

每个提交必须全量测试通过并独立 review 后再推送。不要把 Task 8 与基础出口 squash 成一个大提交；这样即使 policy design 被否决，结构化 spec 能力仍可独立保留和审查。

# OntoPoc 开发冻结与接力记录

最后更新：2026-09-03
状态：**功能开发冻结，等待业务验证或 PR 处理**

## 0. 恢复时先对账

项目：OntoPoc

仓库：`https://github.com/Longado/ontopoc`

开发工作树：`.worktrees/pc-agent-modeling-demo`

分支：`rico/handoff-v2`

功能冻结基线：`61df67b1bd0efe81a4066a4a7db96066b9d7fb7b`

PR：[#12 feat: add five-system multi-agent quality assessment](https://github.com/Longado/ontopoc/pull/12)

冻结时已确认：

- 工作树干净，分支已推送并与 `origin/rico/handoff-v2` 同步；
- PR #12 为 `OPEN`、`MERGEABLE`；
- GitHub Actions `unittest` 已通过；
- PR 尚未合并到 `main`，不能把当前能力写成主分支已发布或产品已交付。

恢复开发前运行：

```bash
cd .worktrees/pc-agent-modeling-demo
git status --short --branch
git rev-parse HEAD
git merge-base --is-ancestor 61df67b HEAD
gh pr view 12 --json url,state,mergeable,statusCheckRollup,headRefOid
```

交接文档本身会形成晚于功能冻结基线的提交，因此恢复时应确认 `61df67b` 仍是当前 HEAD 的祖先，而不是要求 HEAD 恰好等于它。若工作树或 PR 状态与本文不同，以重新读取到的 Git/GitHub 状态为准，不沿用本文的完成判断。

## 1. 为什么冻结

本轮已经完成一个可验证的纵向产品切片，继续增加框架、页面、数据库、工作流或连接器平台不会提高当前业务判断的可信度。

冻结不是项目完成，也不是放弃开发。它表示：

1. 不再主动增加功能或架构；
2. 先让业务人员验证当前判断结果是否有用；
3. 只有真实案例暴露明确阻塞，才恢复一个最小开发任务；
4. PR 评审修复、真实字段映射和已确认的业务验证不受冻结阻止。

## 2. 当前产品问题

当前唯一主场景是制造业质量异常后的临时控制范围判断。

业务痛点：质量人员需要跨 QMS、MES、WMS、ERP、PLM 手工追查批次、版本、库存、发运和客户侧对象，难以及时回答哪些对象应该被控制，哪些可以排除，哪些仍缺数据。

当前唯一主决策：

> 哪些库存、在制、待发运、在途或客户侧对象应进入临时控制或复检队列？

产品不是自动根因分析器，也不是生产执行系统。它把分散事实整理为可检查的候选范围，最终由质量负责人确认。

## 3. 当前可运行的产品链路

```text
ERP / MES / QMS / WMS / PLM 合成只读记录
→ 统一事实快照与稳定 hash
→ Python 确定性计算四态影响范围
→ 决策分析 Agent
→ 本体建模 Agent
→ 证据审查 Agent
→ 决策建议 Agent
→ 人工确认候选
→ 不执行外部写回
```

### 3.1 五系统事实入口

`src/ontology_poc_generator/enterprise_sources.py` 已实现：

- manifest 必须且只能声明 ERP、MES、QMS、WMS、PLM 各一个来源；
- 支持本地 JSON 和 HTTPS GET；
- 每个系统只能声明自己权威范围内的事实类型；
- 记录排序和内容 hash 稳定，不受输入顺序影响；
- `source_record_id` 跨系统唯一；
- HTTP 令牌只能从系统专用环境变量读取，且不会随重定向转发；
- 当前只接受 `synthetic_demo`，不能靠 manifest 自报为生产授权数据。

当前系统语义分工：

| 系统 | 当前权威事实 |
|---|---|
| QMS | 质量事件、识别对象、检验结果 |
| MES | 实际生产对象、批次使用、生产版本、设备 |
| WMS | 库存/物流对象、库存归属、批次和版本 |
| ERP | 订单、客户侧对象及交付关系 |
| PLM | BOM、产品版本和项目映射 |

### 3.2 确定性影响范围

`src/ontology_poc_generator/investigation_scope.py` 已实现四态：

- `confirmed_impact`：对象与异常件存在明确的同批次关系；
- `possible_impact`：存在版本级关联，但批次关系不足；
- `excluded`：对象全部相关批次均有明确正常对照，且不存在未闭合关系；
- `not_evaluable`：缺少批次、版本、BOM 或项目映射等必要关系。

关键约束：

- 质量事件识别的对象必须有明确异常检验结果；
- 正常/异常结果冲突直接拒绝；
- 多批次对象只要仍有未知批次，就不能标记为已排除；
- 重复或冲突的对象类型直接拒绝；
- 每个对象的证据引用都闭合到 QMS 事件、异常检验和后续关系事实；
- `root_cause_confirmed` 固定为 `false`。

### 3.3 多 Agent 建模

多 Agent 已实现，位于：

- `src/ontology_poc_generator/agent_modeling.py`
- `src/ontology_poc_generator/connected_assessment.py`

四个角色按顺序运行：

1. **决策分析 Agent**：从输入材料提取业务决策契约；
2. **本体建模 Agent**：提出对象和关系候选；
3. **证据审查 Agent**：逐项接受、拒绝或指出证据缺口；
4. **决策建议 Agent**：在四态范围内生成 `include / exclude / needs_evidence` 建议。

这里的“多 Agent”是四个独立提示词角色与四次模型调用，不是自主群聊、动态任务分配或长期运行的 Agent 平台。它们可以共用同一个 OpenAI-compatible 模型端点。

Python 仍是契约和状态权威：

- Agent 不能增加范围对象；
- 不能改变四态与建议类型的合法映射；
- 不能伪造或遗漏 evidence refs；
- 判断理由和缺证要求必须与 Python 计算结果一致；
- 不能声称根因已确认、库存已冻结、生产已停止或系统已写回；
- 无效范围会在任何模型调用前被拒绝。

### 3.4 DecisionPack、OntologySpec 与验证

既有编译链继续有效：

```text
候选决策契约
→ DecisionPack
→ OntologySpec
→ 引用闭包检查
→ 合成规则求值
→ ValidationReceipt
```

这些状态的含义必须分开：

- `ready_for_human_confirmation`：候选材料完整到可以人工审查；
- `validation=completed`：固定合成规则已经求值；
- `receipt_recorded`：前端展示了已生成的回执；
- `pass`：合成输入满足候选规则。

它们都不等于人工已同意、本体已发布、客户已验收或外部动作已完成。

在冻结之后经明确授权增加了一项窄范围 Adapt：`implementation_map.v1`。它只从同一组 `DecisionPack / OntologySpec` 派生，不改变两者内容，也不是第二套模型权威。映射逐项记录：

- 对象、关系、属性或规则的稳定 ID 与 semantic key；
- 编译来源及可解析的 `source_ref_ids`；
- 当前真实存在的 Python 实现入口；
- `declared_only / runtime_input / runtime_executable` 三种实现状态。

生成时会校验 OntologySpec 的 pack hash，拿错 DecisionPack 与 OntologySpec 会直接拒绝。对象和关系当前标为 `declared_only`，这是对运行能力缺口的如实暴露，不代表系统已经根据这些声明自动生成数据库、接口或页面。

### 3.5 CLI

实现映射入口：

```bash
PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/supply_chain_exception.json \
  --knowledge-unit knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json \
  --ontology-spec-output /tmp/ontology-spec.json \
  --implementation-map-output /tmp/implementation-map.json
```

五系统联合评估入口：

```bash
PYTHONPATH=src python -m ontology_poc_generator.connected_assessment_cli \
  tests/fixtures/enterprise_sources/manifest.json \
  --output /tmp/connected-quality-assessment.json
```

模型配置只通过环境变量提供：

```bash
export EIP_MODEL_API_BASE=<openai-compatible-base>
export EIP_MODEL_NAME=<model-name>
export EIP_MODEL_API_KEY=<secret>
```

冻结时本机未配置这三个变量，因此没有完成真实 DeepSeek 调用。不能把 fake gateway 测试写成 DeepSeek 已联通。

### 3.6 当前界面

当前界面能够读取仓库内固定的合成质量调查 artifact，并展示：

- 当前质量事件和主决策；
- 确定影响、可能影响、已排除、无法评估四类对象；
- 候选原因、正常对照、反证和数据缺口；
- FDE 对对象/关系候选的会话内调整；
- 质量负责人对控制范围的会话内选择；
- DecisionPack、OntologySpec、hash、引用和 ValidationReceipt。

界面尚未实时调用 Python CLI 或模型；选择结果不持久化，也不产生真实任务或系统动作。

## 4. 当前明确未实现

以下内容不能在演示、PR 或对外说明中写成已完成：

1. 客户真实 ERP、MES、QMS、WMS、PLM 接口联通；
2. SAP 或其他厂商专用适配器；
3. 客户字段映射、身份认证、网络连通和数据质量验收；
4. DeepSeek 在线端到端运行；
5. 真实数据范围的 OntologySpec 和 ValidationReceipt；
6. 浏览器实时调用建模后端；
7. 决策保存、恢复、多人审批、责任人和任务状态；
8. 真实冻结、停产、发运拦截或任何外部写回；
9. 客户效果、节省时间、降低漏控或降低误控的证据；
10. 正式部署、账号、多租户、审计后台和生产运维。

## 5. 本轮过程复盘

### 5.1 做对了什么

- 从“建设本体平台”收缩到一个质量经理需要完成的具体决定；
- 把业务系统事实、Python 判断、Agent 候选和人工决定分成四种权威；
- Agent 输出不是直接相信，而是逐字段通过确定性合同校验；
- 保留 `not_evaluable`，没有为了演示完整度猜测缺失关系；
- 先使用合成、公开数据完成端到端，不把客户材料发送给模型或写入公开仓库；
- 开源项目只作为语义和进入条件参考，没有 fork 或引入大型依赖；
- 通过独立对抗审查发现并修复令牌泄露、错误排除、异常冲突、重复类型和证据链不闭合问题。

### 5.2 走过的弯路

- 前期计划一度扩展到 DemoBundle、ValidationReceipt、EIP、Temporal、BaSyx、Ontop 等完整架构，离客户当前痛点过远；
- 曾把“验证更完整”误当成“产品价值更强”，增加了用户难以感知的内部合同讨论；
- 多 Agent 容易被设计成独立平台，后来才收缩为四个可验证角色；
- 一度允许 `authorized_read_only`，但下游 OntologySpec 仍固定为 `synthetic_demo`，证据口径不一致；最终选择诚实拒绝，而不是扩 schema；
- 第一版排除逻辑对混合批次和缺失关系过于乐观，复审后改成 fail closed；
- 第一版让模型自由填写理由与缺证文本，可能与系统边界冲突；最终改为精确复制确定性结论。

### 5.3 固化下来的判断

1. 产品价值来自“能否帮助质量负责人更快、更少漏控地确定控制范围”，不是对象数量或 Agent 数量；
2. 多 Agent 负责提出和审查候选，不能取代状态机、证据闭包和人工裁决；
3. 当前主决策不是自动确认根因，而是确定临时控制/复检范围；
4. 真实连接的第一步不是写五个厂商 SDK，而是取得五份脱敏字段样例并完成映射；
5. 没有第二个真实调用者时，不增加通用适配器、仓储层或工作流引擎；
6. Open-source 只在出现真实阻塞时进入：Trace-X 参考追溯语义，LinkML/pySHACL/Ontop/BaSyx 暂不引入当前运行时。

## 6. 冻结验证证据

冻结提交 `61df67b` 的验证结果：

- 后端：296 tests，全部通过；
- 前端 unit/story：92 tests，全部通过；
- Sites：4 tests，全部通过；
- Vite build：1973 modules transformed，构建成功；
- 质量调查 artifact `--check`：通过；
- `compileall`：通过；
- `git diff --check`：通过；
- 独立对抗复审：未发现 P1/P2；
- PR #12 GitHub Actions `unittest`：通过。

2026-09-03 的窄范围 `implementation_map.v1` Adapt 验证：

- 后端：299 tests，全部通过；
- 两个 committed artifact `--check`：通过；
- `compileall` 与 `git diff --check`：通过；
- CLI 实际生成 7 个映射元素：4 个 `declared_only`、2 个 `runtime_input`、1 个 `runtime_executable`。

本地复核命令：

```bash
PYTHONPATH=src python -m unittest discover -s tests -q
PYTHONPATH=src python scripts/generate_quality_investigation_artifact.py --check
PYTHONPATH=src python -m compileall -q src tests scripts
git diff --check

cd landing-page
npm run test:unit
npm run test:sites
npm run build
```

构建有一个 JavaScript chunk 超过 500 kB 的非阻塞警告。当前没有证据证明它影响质量场景演示，不为此单独做代码拆分。

## 7. 恢复开发的唯一推荐入口

恢复时不要先增加网页或架构。推荐顺序：

1. 由用户提供或确认五系统的脱敏字段/示例 payload；真实材料只放 `.local-sensitive/`；
2. 为一个留出质量事件建立 ERP/MES/QMS/WMS/PLM 字段映射；
3. 在本地环境配置 DeepSeek 或其他 OpenAI-compatible 模型，运行四 Agent；
4. 让一名质量业务人员核对五类对象、四态结果、证据和缺口；
5. 对比人工追查的耗时、漏控、误控与待补证质量；
6. 只有业务人员给出 `go` 且指出具体阻塞，才恢复下一轮开发。

可能的下一轮只能选择一个：

- 如果阻塞是字段差异：增加一份明确的 source mapping；
- 如果阻塞是模型不稳定：建立小型 held-out prompt regression；
- 如果阻塞是无法续办：增加最小持久化；
- 如果阻塞是外部动作回执：单独设计受控 action contract。

不能同时开展这些方向。

## 8. 清空历史后的接力 Prompt

```text
接手 OntoPoc 前，先完整阅读：
docs/DEVELOPMENT_HANDOFF.md

当前功能开发已经冻结。先执行第 0 节对账，确认 branch、HEAD、PR 和 CI；不要把文档快照当成实时状态。

产品当前只解决制造业质量异常后的临时控制范围：从 ERP/MES/QMS/WMS/PLM 合成只读事实计算确定影响、可能影响、已排除、无法评估，再由四个证据受约束的 Agent 形成候选，最终人工确认。

不要声称真实客户接口、DeepSeek 在线调用、持久化审批或外部写回已经完成。不要把客户敏感材料放入仓库或发送给外部模型。

如果用户没有提供新的业务验证、脱敏字段样例或明确 PR 评审意见，只报告当前状态，不继续开发。如果用户授权恢复开发，先写 Pain、Decision、Outcome、Non-goals、Smallest path、Proof，并且一次只解决一个真实阻塞。
```

# Ontology POC Generator

**English summary.** OntoPoc compiles one industrial business decision into an evidence-bound, testable, traceable `DecisionPack`. The current scenario: after a manufacturing quality incident, which inventory, work-in-progress, shipping, in-transit or customer-side objects should enter temporary control or re-inspection. Synthetic read-only facts from ERP, MES, QMS, WMS and PLM are snapshotted and hashed, Python deterministically computes four states (confirmed impact, possible impact, excluded, not evaluable, failing closed on missing evidence), four prompt-role agents propose and audit candidates under that contract, and a human quality owner makes the final call. Nothing is written back to any system. Real customer interfaces, live model runs and persistence are not implemented; see `docs/DEVELOPMENT_HANDOFF.md` for the frozen state. Documentation below is in Chinese.

把一个工业业务决策编译成有来源、可测试、可追溯的 `DecisionPack`。当前项目是 Evidence-bound Decision Compiler 的 recorded artifact 版本，不是已经成形的新 EIP。

> 开发前先读[最小产品开发护栏](docs/DEVELOPMENT_GUARDRAILS.md)。它先判断本轮是否直接推进用户决策，再决定是否需要实现；长期架构不自动授权当前建设。

## 产品闭环

```text
场景参数
-> 业务决策卡
-> 对象/关系/规则/数据草案
-> DecisionPack / OntologySpec
-> 合成事实确定性验证与 ValidationReceipt
-> 静态 artifact 与浏览器只读投影
```

当前本地分支已在确定性 Proposal CLI 之上完成有来源知识辅助、`DecisionPack → OntologySpec` 编译、无状态合成验证，以及质量场景的五系统只读接入与多 Agent 建模。通用接入契约支持从 ERP、MES、QMS、WMS、PLM 的本地 JSON 或 HTTPS GET 读取规范化事实；它不是任何特定厂商接口已经联通的证明。POC 产物仍是 `synthetic_demo` 资产；人工确认、版本发布、真实客户接口验收与受控写回尚未实现。旧 EIP 只作为行为参考，不复制其模块或数据库。

当前产品主线收敛为一个决策：质量异常发生后，哪些库存、在制、待发运、在途或客户侧对象进入临时控制或复检队列。系统只提出候选范围和证据，最终选择仍由质量负责人确认。

## 公开场景自动搭建本体（本地）

给一份公开数据快照和一个业务问题，模型根据字段目录提出本体（对象类型、身份字段、关系、忽略字段、数据缺口），Python 拿全部记录核验：字段存在、同一对象在不同来源用同一套身份键、每个字段要么用上要么写明忽略、事件 / 受影响对象 / 部件机制 / 信号四个角色齐全、关系在数据里真有连接、两个来源真的连上。核验出错就把错误回传模型重做，错误数不再减少就停。通过后按本体回答召回范围问题，并让模型逐条读投诉原文，判断是不是同一个缺陷。

快照 `examples/nhtsa/chevrolet_bolt_2017_2023.json` 是 2026-09-13 从 NHTSA 公开接口取的 Bolt EV / EUV 2017–2023 召回和投诉（13 个召回活动、679 条投诉）。这是 `public_data`，不进入 `synthetic_demo` / OntologySpec / ValidationReceipt 链路；本体格式是 `public_ontology.v1`。

```bash
# 在线运行（需要本机 DeepSeek 凭据，见 docs/HANDOFF_2026-09-13.md 第 9 节）
PYTHONPATH=src:. python scripts/run_public_ontology.py \
  --campaign 21V650000 --campaign 21V517000 --output output/public-ontology-<时间>.json

# 取另一个车型的快照
PYTHONPATH=src:. python scripts/fetch_nhtsa_snapshot.py \
  --make chevrolet --model "bolt ev" --years 2017-2023 --output examples/nhtsa/<名称>.json
```

页面：`npm --prefix landing-page run dev` 后打开首页，默认场景"汽车召回范围研判（NHTSA）"读 `landing-page/public/data/nhtsa-bolt-review-pack.json`，不需要本机 Python 服务；确认本体后逐条复核候选投诉，复核结果存在本机浏览器，可下载。更新运行报告后用 `PYTHONPATH=src:. python scripts/build_public_review_pack.py` 重建页面数据（`--check` 验证未过时）。

边界：范围只到车型年款（召回数据没有车架号）；投诉原文判断是候选，待质量工程师复核，提示词换措辞结论会明显变化，校准前不能当结论；四个角色是为"召回范围研判"这一类问题设计的，不是任意问题的通用本体平台；两个来源部件命名不同时会漏检（如刹车召回 0 条候选），见方案文档。方案与试验证据见 `docs/NHTSA_AUTO_ONTOLOGY_PLAN.md`。

## 公开召回范围核对（本地）

新增一个独立的公开历史案例：openFDA 事件 **95876**，Russ Davis 2024 年黄瓜与加工食品召回。
原始响应与人工核对的范围表保存在 `examples/recalls/`，覆盖 5 条召回记录、12 个产品分段和 93 条产品—批号对应关系。
这是 `public_recall` 数据，不进入既有 `synthetic_demo` / OntologySpec / ValidationReceipt 链路。

核对一项产品：

```bash
PYTHONPATH=src python -m ontology_poc_generator.recall_cli \
  --product F-0369-2025/1 --lot X7547814
```

`--product` 接受范围表中的完整产品名称或 product_key；也可仅用 `--upc 795631810387` 标识产品。
`--label-date 2024-11-15` 为可选的包装 Use/Sell By 日期，不是生产日期。
返回 `matched / insufficient / conflict / not_matched`，每项附带原文和来源。匹配表示产品身份与列明批号匹配；没有提供日期时不核验日期。
未匹配不代表安全；没有真实库存、逐批投料、正常检验或已执行控制的含义。公告已列明批号也不代表逐件检验阳性。

在两个终端启动本地核对 API 与已有页面：

```bash
# 终端一：仓库根目录；仅监听本机，无模型调用或数据写回
PYTHONPATH=src python -m ontology_poc_generator.recall_server

# 终端二
cd landing-page
npm ci
npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

打开 `http://127.0.0.1:5178`，默认进入事件 95876 核对清单。添加一行或使用 3 行练习示例，核对后逐行修正、补证或复核。练习输入不是实际库存。页面实时请求本地 Python，前端不重复实现匹配逻辑。

支持从表格粘贴最多 100 行：不含表头，按产品名称或公告编号、批号、UPC、Use/Sell By 日期（YYYY-MM-DD）四列排列，用 Tab 分隔，空单元格保留。不是任意 Excel 文件导入。

清单与已保存复核保存在当前浏览器/源站的 localStorage，切换场景或刷新可恢复；修改一行只清除该行旧结果和复核，来源版本变化后须重新核对。保存失败会提示下载摘要；损坏或不支持的草稿不会自动覆盖，可下载原始草稿后明确重置。“下载核对摘要”保存本地 JSON，含逐行结果、补证事项和范围说明；经办人是手工备注，不是认证身份或审批。

辅助入口“示例建模（只读）”仍是固定合成案例，其会话选择不属于召回清单。现有静态 Sites 部署没有此 Python API，不代表云端已接入。

本轮交互问题与验收记录见 [问题台账](docs/PM_INTERACTION_ISSUES.md) 和 [修改步骤](docs/superpowers/plans/2026-09-12-event-worklist-interaction.md)。

DeepSeek 公告提取实测：

```bash
# 在本机安全配置 DEEPSEEK_API_KEY（也兼容 EIP_MODEL_API_KEY）；不要将密钥写入仓库。
PYTHONPATH=src python scripts/check_recall_deepseek.py \
  --model deepseek-flash --output output/recall-deepseek.json
```

脚本向 DeepSeek 官方端点发送 5 条公开公告，每条一次调用，仅提取产品与批号分组；输入不含人工核对答案。
报告保留模型返回标识、耗时、候选与逐产品差异，任何遗漏、多出、串品或重复均不通过；模型输出不会覆盖范围表。
2026-09-12 使用官方 `deepseek-flash` 完成一次在线测试：5/5 公告、12 个产品分段、93 条批号对应关系与核对表一致。
该测试衡量公告提取能力，不是召回预测或业务效果。密钥缺失时退出码 2，不生成成功报告；重复运行须指定新报告路径。

检查命令与逐轮计划见 [本轮实施计划](docs/superpowers/plans/2026-09-12-public-recall-scope.md)。

## MVP 输入

参考 [`examples/dairy_rnd.json`](examples/dairy_rnd.json)：

- 行业与场景名称；
- 要支持的一个核心业务决策；
- 决策触发条件、决策者和参与角色；
- 已知业务对象、约束和期望行动；
- 可用数据源及数据状态；
- POC 希望验证的问题。

## MVP 使用方式

```bash
PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/dairy_rnd.json \
  --output output/dairy-rnd-poc.md
```

运行测试：

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

显式加载首个供应链知识单元并输出结构化 JSON：

```bash
PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/supply_chain_exception.json \
  --knowledge-unit knowledge/supply_chain/supplier_evidence_boundary_v1.json \
  --format json \
  --output output/supply-chain-decision-pack.json
```

知识加载是 opt-in：不传 `--knowledge-unit` 时，JSON 和 Markdown 保持 Loop 0 的默认投影。当前知识单元只提出供应商资格、历史供货、数据需求、验收问题和入队政策缺口等有来源候选建议；它不会给出最终订单队列或处置动作。

需要检查模型元素是否真正进入运行逻辑时，可额外输出只读实现映射：

```bash
PYTHONPATH=src python -m ontology_poc_generator.cli \
  examples/supply_chain_exception.json \
  --knowledge-unit knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json \
  --ontology-spec-output output/ontology-spec.json \
  --implementation-map-output output/implementation-map.json
```

`implementation_map.v1` 从当前 `DecisionPack` 和 `OntologySpec` 派生，不是新的可编辑权威源。它逐项列出对象、关系、属性和规则的来源引用、当前 Python 消费者，以及 `declared_only / runtime_input / runtime_executable` 状态；其中 `declared_only` 明确表示元素目前只参加契约与引用闭包检查，不能宣称已有业务运行行为。

## 多 Agent 自动建模

`ontopoc-agent-model` 已接入现有编译链，不再只输出对象提及：

1. 决策分析 Agent 提取核心决策、负责人、触发条件、约束、数据源和验收问题；
2. 本体建模 Agent 识别质量对象类型及其直接关系；
3. 证据审查 Agent 对全部候选逐项接受或驳回；
4. Python 校验证据、稳定身份和关系闭包，材料完整时生成 `DecisionPack` 与 `OntologySpec`。

使用 OpenAI-compatible 模型运行合成质量场景：

```bash
export EIP_MODEL_API_BASE=https://api.deepseek.com
export EIP_MODEL_NAME=deepseek-v4-flash
export EIP_MODEL_API_KEY=<your-api-key>

PYTHONPATH=src python -m ontology_poc_generator.agent_modeling_cli \
  examples/quality_multi_agent_modeling.txt \
  --output output/quality-multi-agent-model.json
```

成功建模时状态为 `ready_for_human_confirmation`，并带有闭合的候选规格；材料缺少负责人、触发条件、验收问题或足够对象时状态为 `blocked_missing_evidence`，不会伪造完整结果。两种状态都不代表人工确认、权威本体更新、发布或真实业务动作。

## ERP / MES / QMS / WMS / PLM 联合评估

`ontopoc-connected-assess` 把五类只读来源接成一条后端产品闭环：

```text
五系统事实
-> 规范化 source snapshot + hash
-> 批次/版本/正常对照/缺失关系的确定性范围计算
-> 三 Agent 建模与证据审查
-> 决策建议 Agent
-> 人工确认候选；不写回外部系统
```

使用仓库内合成五系统 fixture 运行：

```bash
export EIP_MODEL_API_BASE=https://api.deepseek.com
export EIP_MODEL_NAME=deepseek-v4-flash
export EIP_MODEL_API_KEY=<your-api-key>

PYTHONPATH=src python -m ontology_poc_generator.connected_assessment_cli \
  tests/fixtures/enterprise_sources/manifest.json \
  --output output/connected-quality-assessment.json
```

Manifest 必须且只能包含 ERP、MES、QMS、WMS、PLM 各一个来源。`json_file` 用于脱敏文件或合成联调；`http_json` 只执行 HTTPS GET，并分别只接受 `ERP_READ_TOKEN`、`MES_READ_TOKEN`、`QMS_READ_TOKEN`、`WMS_READ_TOKEN`、`PLM_READ_TOKEN`，令牌不会随重定向转发。连接端返回统一的 `records` 数组，业务系统仍是记录权威。

影响范围不是 Agent 自由生成：Python 根据显式关系计算 `confirmed_impact / possible_impact / excluded / not_evaluable`。决策建议 Agent 只能在对应状态下提出 `include / exclude / needs_evidence`，必须完整复用已计算的 evidence refs；不能增加对象、确认根因或声称已执行控制。

## 文档

- [开发前必读：最小产品开发护栏](docs/DEVELOPMENT_GUARDRAILS.md)
- [产品定义](docs/PRODUCT_SPEC.md)
- [产品需求文档 PRD](docs/PRD.md)
- [技术架构](docs/TECHNICAL_ARCHITECTURE.md)
- [滚动阶段路线图](docs/ROADMAP.md)
- [发现与决策记录](docs/DISCOVERY_LOG.md)
- [技术架构图](docs/design/README.md)
- [历史参考：渐进式 EIP 重建总计划](docs/superpowers/plans/2026-08-29-incremental-eip-reconstruction.md)
- [首版 MVP 实施记录](docs/superpowers/plans/2026-08-29-ontology-poc-generator-mvp.md)

## 当前边界

- 生成的是 POC 讨论与实施方案，不代表项目批准或客户验收；
- 缺少客户真实数据时，输出必须标明使用合成演示数据；
- 已实现五系统通用只读接入契约和合成端到端联调，但尚未取得或验收任何客户厂商接口、字段映射与凭据；
- 不执行 ERP、MES、QMS、WMS、PLM 外部写回，也不自动冻结、停产或拦截发运；
- 第一版不以“对象数量”作为 POC 成功指标，成功标准是一个业务决策闭环可被客户纠正和验收。
- 当前生成器尚不等于新 EIP；只有完成对应 Loop 的测试和黄金场景证据后，能力才可标记为已实现；
- 当前已有 draft/candidate `OntologySpec`、`categorical_all_of_v1` 四态运行时和录制式 `ValidationReceipt` 展示，但 `validation=completed` / `receipt_recorded` 只表示固定合成验证已记录，规则 `pass` 只表示规则匹配；两者都不等于人工 review、publication、Action、客户确认、业务事实或生产结论。

# Ontology POC Generator

从本体建设 POC 方案生成器出发，渐进重建一套新的 EIP：把一个工业业务决策编译成有来源、可审查、可测试、可版本化和可修正的 `DecisionPack`。

## 产品闭环

```text
场景参数
-> 业务决策卡
-> 对象/关系/规则/数据草案
-> DecisionPack / OntologySpec
-> 合成事实确定性验证与 ValidationReceipt
-> 人工审查与修订
```

当前本地分支已在确定性 Proposal CLI 之上完成首个 opt-in 的有来源知识辅助 Loop、`DecisionPack → OntologySpec` 编译和无状态合成验证。固定 Demo artifact 记录 `validation_run.v1`：4 个合成 case 分别对 baseline/candidate 求值，生成 8 个真实、带 canonical receipt hash 并绑定 pack/spec/facts hash 的 `ValidationReceipt.v1`；PC Validation 页面只投影这些后端回执。POC Markdown/JSON、`OntologySpec` 和回执仍是 `synthetic_demo` 资产；人工审查、版本、发布、真实数据接入与受控行动尚未实现。旧 EIP 只作为行为参考，不复制其模块或数据库。

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

## 文档

- [产品定义](docs/PRODUCT_SPEC.md)
- [产品需求文档 PRD](docs/PRD.md)
- [技术架构](docs/TECHNICAL_ARCHITECTURE.md)
- [滚动阶段路线图](docs/ROADMAP.md)
- [发现与决策记录](docs/DISCOVERY_LOG.md)
- [技术架构图](docs/design/README.md)
- [渐进式 EIP 重建总计划](docs/superpowers/plans/2026-08-29-incremental-eip-reconstruction.md)
- [首版 MVP 实施记录](docs/superpowers/plans/2026-08-29-ontology-poc-generator-mvp.md)

## 当前边界

- 生成的是 POC 讨论与实施方案，不代表项目批准或客户验收；
- 缺少客户真实数据时，输出必须标明使用合成演示数据；
- 第一版不自动连接 ERP/MES，不执行外部写回；
- 第一版不以“对象数量”作为 POC 成功指标，成功标准是一个业务决策闭环可被客户纠正和验收。
- 当前生成器尚不等于新 EIP；只有完成对应 Loop 的测试和黄金场景证据后，能力才可标记为已实现；
- 当前已有 draft/candidate `OntologySpec`、`categorical_all_of_v1` 四态运行时和录制式 `ValidationReceipt` 展示，但 `validation=completed` / `receipt_recorded` 只表示固定合成验证已记录，规则 `pass` 只表示规则匹配；两者都不等于人工 review、publication、Action、客户确认、业务事实或生产结论。

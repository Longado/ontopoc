# Ontology POC Generator

从本体建设 POC 方案生成器出发，渐进重建一套新的 EIP：把一个工业业务决策编译成有来源、可审查、可测试、可版本化和可修正的 `DecisionPack`。

## 产品闭环

```text
场景参数
-> 业务决策卡
-> 对象/关系/规则/数据草案
-> 决策闭环与演示剧本
-> 验收问题、交付物和风险边界
-> 人工审查与修订
```

当前版本仍是确定性 Proposal CLI。POC Markdown 是演进起点而非产品终点；后续按独立 Loop 逐步加入知识辅助建模、本体规格、无状态验证、人工审查、版本、数据血缘和受控行动。旧 EIP 只作为行为参考，不复制其模块或数据库。

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
- 当前生成器尚不等于新 EIP；只有完成对应 Loop 的测试和黄金场景证据后，能力才可标记为已实现。

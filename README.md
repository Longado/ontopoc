# Ontology POC Generator

本体建设 POC 方案生成器：用本体方法论设计本体项目本身，输入工业场景参数，生成可讨论、可审查、可验收的定制化 POC 方案。

## 产品闭环

```text
场景参数
-> 业务决策卡
-> 对象/关系/规则/数据草案
-> 决策闭环与演示剧本
-> 验收问题、交付物和风险边界
-> 人工审查与修订
```

第一版采用确定性方法论内核，不依赖大模型即可生成结构完整的 Markdown 方案。后续可以接入 LLM 做材料抽取、候选补全和读者化改写，但不能绕过结构校验和人工确认。

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
- [原型与技术架构图](docs/design/README.md)
- [MVP 实施计划](docs/superpowers/plans/2026-08-29-ontology-poc-generator-mvp.md)

## 当前边界

- 生成的是 POC 讨论与实施方案，不代表项目批准或客户验收；
- 缺少客户真实数据时，输出必须标明使用合成演示数据；
- 第一版不自动连接 ERP/MES，不执行外部写回；
- 第一版不以“对象数量”作为 POC 成功指标，成功标准是一个业务决策闭环可被客户纠正和验收。

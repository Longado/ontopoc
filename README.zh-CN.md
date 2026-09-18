<picture>
  <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
  <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc — Draft the ontology. Show the evidence." width="420">
</picture>

# OntoPoc — Draft the ontology. Show the evidence.

[English](README.md) · 中文

交一份客户的业务表或流程文档，几分钟内得到一份本体草案——业务里有哪些对象、各自按什么识别、彼此怎么关联——以及它哪里有证据、哪里靠不住。然后你逐项说哪些对，这份判断会被存下来，同一份文件下次上传就从它开始。

给实施顾问和本体团队用。本机运行，文件和结果不出这台机器。

## 怎么做的

**模型提议，代码核验，人决定。** 模型只看字段名和少量示例值，提出对象、识别字段和关系；代码拿每一行核验，出错退回重做，最多三次。每次上传同时建三次本体，代码对齐后标出三次对不上的地方——那些正是模型拿不准、该由人决定的地方。

**每句话都是算出来的，不是说出来的。** 数据体检由代码逐行算七项：字段有没有去处、同一编号信息打不打架、编号写法是否统一、关系是否真连上、引用的对象找不找得到、表和表连不连得上、每张传上来的表都真的被用上了。然后模型把业务问题写成结构化查询，答案由代码在数据上算出（数个数、算占比、求和、求平均、按几样东西分组）；答不了时写明是本体缺了、数据里没有，还是这种问法还不支持。

**人的判断能过夜。** 顾问对每个对象、每条关系判对不对，可以改名、补漏。同一个东西的两种写法（全称与简称）由模型提候选、代码拿数据核对、人决定采纳——不自动合并，也不改数据。确认存成这份文件的参考本体：同一份文件下次上传自动对照，并把上次的判断预填好，只剩有差别的要看。对象改了名不会被当成丢了，因为对应是按"读同一张表、用同样的识别字段"认的，不是按名字。

## 验到什么程度

还没有真实客户用过，也没有部署。已经验过的是这些：

- **芝加哥市政府合同 3000 条。** 按部门求和 4,631,003,200，与 Python 逐行相加一分不差。名称对应提出"PLANNING & DEVELOPMENT"对应"DEPARTMENT OF PLANNING AND DEVELOPMENT"（140 条对 3 条），以及车队管理部门那一组（67 条对 12 条）；人采纳后重传同一份文件，一组由模型重新提出，另一组靠上次的确认带回来。
- **Chinook 发票 412 条。** 平均单张 5.65，与 Python 一致。
- **UCI 英国零售交易**、**一家上市公司的关联交易管理制度（PDF）**：各自逼出过问题，都已修掉。
- **合成的示例制造公司**（四张表）和它的售后流程文档，里面故意埋了两个问题，数据体检都能查出来。
- 历次运行累计问过 306 道真实业务问题；每一轮验了什么、怎么验的，记在 `docs/PRD_ITERATION_5.md`。

测试：后端 358、页面 128，每个 PR 都跑。

## 边界

- 本体是模型的提议。核验通过只说明它和数据对得上，不说明它是业务上最好的划分。
- 查询还不能按数值条件筛选、不能限定时间段、一道题里给不了两个数。
- 属性列里的同义写法不在射程内：名称对应只管"靠一个名字识别的对象"。代价见 `docs/PRD_ITERATION_5.md` 第 8 节。
- 确认按文件哈希记忆，客户发来新版文件（哪怕多一行）就对不上，而且不会提示。
- 表格和文档现在分开建模，还不能把同一业务的表和文档合在一起。
- 发给模型的只有每列的字段名、每列最多 3 个示例值、取值不超过 12 种的列的全部取值（文档则是正文）。上传页可以在发送前逐列看清楚。

## 跑起来

```bash
# 页面
cd landing-page && npm ci && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
# 本机建模服务（端口 8767，需要本机 DeepSeek 凭据；结果留在 output/ontology-runs/）
PYTHONPATH=src python -m ontology_poc_generator.ontology_server
```

打开 `http://127.0.0.1:5178`。没有服务也能打开两份内置的示例结果：合成公司的工作簿和它的售后流程文档。改了后端要重启建模服务，页面遇到旧版本时会直接说。

```bash
PYTHONPATH=src python -m unittest discover -s tests -q          # 后端测试
npm --prefix landing-page run test:unit                         # 页面测试
PYTHONPATH=src:. python scripts/run_company_ontology.py --file examples/company/demo_company.xlsx --output output/demo-run.json
PYTHONPATH=src:. python scripts/make_demo_company.py            # 重新生成合成示例工作簿
```


页面上的每个功能也都是一个标准 MCP 工具（stdio，25 个），Claude Code 或任何 MCP 客户端都能直接调：`claude mcp add ontopoc -- env PYTHONPATH=$PWD/src python3 -m ontology_poc_generator.mcp_server`。说明见 `docs/MCP.md`。

## 示例场景：车辆召回范围研判

同一套"模型提议、代码核验"用在 NHTSA 召回公告和车主投诉上，算出每个召回范围内外的同类投诉，由质量工程师逐条复核（雪佛兰 Bolt EV / EUV 2017–2023、现代 Kona Electric 2019–2021）。入口在页面侧边栏"更多示例"下，读 `landing-page/public/data/` 里的静态文件，不需要 Python 服务。命令和代码位置见 [docs/RECALL_EXAMPLE.md](docs/RECALL_EXAMPLE.md)。

数据来自 NHTSA 公开接口。OntoPoc 与 NHTSA、通用汽车、现代汽车无关联；候选和模型初判不是官方结论，不构成缺陷认定，复核也不代表缺陷成立或车辆被召回。

## 代码位置

| 文件 | 作用 |
|---|---|
| `src/ontology_poc_generator/company_sources.py` | 读上传的表格和文档，单份或一批 |
| `src/ontology_poc_generator/company_ontology.py` | 建模提示词与"建了再核、核不过重来"的循环 |
| `src/ontology_poc_generator/public_ontology.py` | 字段目录、本体核验（17 类错误）、对象图 |
| `src/ontology_poc_generator/ontology_eval.py` | 七项数据体检，逐行算 |
| `src/ontology_poc_generator/ontology_questions.py` | 业务问题，以及代码执行的结构化查询 |
| `src/ontology_poc_generator/name_variants.py` | 同一个东西的两种写法：只提数据撑得住的候选，绝不自动合并 |
| `src/ontology_poc_generator/ontology_confirm.py` | 人的判断、它变成的参考本体、下次的预填 |
| `src/ontology_poc_generator/ontology_acceptance.py` | 1 到 3 道固定验收问题，以及它们怎么扛住改名 |
| `src/ontology_poc_generator/ontology_compare.py` | 按"从什么建出来的"对照两份本体 |
| `src/ontology_poc_generator/ontology_server.py` | 页面对接的本机服务 |
| `landing-page/src/OntologyStudio.jsx` | 工作台：上传、本体、数据体检、问答、确认 |
| `landing-page/src/*Model.js` | 页面的纯函数，各自带测试 |

## 方向与文档

项目 2026-08-29 起步时是售前 POC 方案编译器，先后经过供应链、合成质量演示、食品召回、召回范围研判，2026-09-14 定为"上传文件自动建本体并自动评测"，召回研判留作示例。删掉的旧线在标签 `archive-2026-09-13-nhtsa-review`。

开发前先读[开发护栏](docs/DEVELOPMENT_GUARDRAILS.md)。

| 文档 | 写什么 |
|---|---|
| [docs/PRODUCT.md](docs/PRODUCT.md) | 产品是什么、站在哪几层、产出什么 |
| [docs/FEATURES_2026-09-16.md](docs/FEATURES_2026-09-16.md) | 一次上传会发生什么、代码在哪、已知边界 |
| [docs/PRD_ITERATION_5.md](docs/PRD_ITERATION_5.md) | 最近一轮：做了什么、怎么验的、没覆盖什么 |
| [docs/PRD_ITERATION_6.md](docs/PRD_ITERATION_6.md) | 当前计划 |
| [docs/DEVELOPMENT_GUARDRAILS.md](docs/DEVELOPMENT_GUARDRAILS.md) | 红线，以及等触发再做的方向 |

License: MIT.

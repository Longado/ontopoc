<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
    <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc" width="360">
  </picture>
</p>

<h1 align="center">OntoPoc</h1>
<p align="center"><strong>团队用的本体平台：每个定义都对照数据检查、由一位具名的人确认；没确认的、数据变了之后过时的，问答拒答并说明原因。</strong></p>
<p align="center">数据集 → 管道 → 对象类型、关系、视图、行为、派生属性 → 问答、看板、智能体（MCP）。</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue" alt="AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/tested%20on-macOS-black" alt="tested on macOS">
  <img src="https://img.shields.io/badge/Python-3.11%2B-green" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Node-22%2B-green" alt="Node 22+">
  <img src="https://img.shields.io/badge/status-Alpha-orange" alt="Alpha">
</p>

<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="https://longado.github.io/ontopoc/">Docs</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="docs/LEGACY_SCREEN.md#快速体验">快速体验</a> ·
  <a href="#用-mcp--claude-接入">MCP / Claude</a> ·
  <a href="#本体-faq">本体 FAQ</a> ·
  <a href="#参与共建">参与共建</a>
</p>

<p align="center"><sub>Ontology tool for MCP / Claude · Docs: <a href="https://longado.github.io/ontopoc/">longado.github.io/ontopoc</a> · Follow on X: <a href="https://x.com/linyutai120479">@linyutai120479</a></sub></p>

<p align="center">
  <img src="docs/media/ontopoc-hero.gif" alt="OntoPoc 蓝色角色将业务表格连接为等待确认的本体关系草案" width="960">
</p>
<p align="center"><sub>功能主题插画 · <a href="docs/media/ontopoc-poster.png">静态版</a> · <a href="docs/media/ontopoc-motion.mp4">MP4</a></sub></p>

OntoPoc is an ontology tool for MCP / Claude: it drafts object types, relations and definitions from business tables or a database, checks them against the data, and lets a named person confirm each one. It is not a knowledge-graph platform and has no durable instance store; it sits ahead of a knowledge graph or semantic layer, so Q&A and agents use only confirmed definitions.

OntoPoc 还在开发中，还没有作者以外的用户。现在的主线是一个团队用的应用（页面根地址 `/`）：上传表格或只读连接 PostgreSQL / MySQL，建数据集和管道，从数据建对象类型、关系、视图、行为和派生属性；每一项都由代码对照数据检查，由另一位建设者确认，并记下确认时的数据版本。问答、看板和智能体只用已确认的定义；数据变了，受影响的定义回到“需要再看”，用到它们的问题拒答并说出是哪一项、谁能确认。

## 团队应用

| 部分 | 做什么 |
|---|---|
| 账号与权限 | 本机账号（管理员、建设、查看三种角色），服务端会话；管理员可按对象类型限定人、按行限定人（只有允许清单），可以让某列的值不发给模型 |
| 数据 | 数据集：上传 CSV / Excel，按主键更新或覆盖，每次一个新版本；数据源：只读连接 PostgreSQL、MySQL，可校验证书；调度：按小时、每天定时拉取或运行管道 |
| 管道 | 过滤、连接、分组统计、去重、计算列等算子，表达式编辑器；合并（按列名接起几步的行：类型不同、缺列、代码含义不同都会拒绝，同一行出现在几个输入里会数出来）和拆分（每行进第一个满足条件的分支，可加“其余”分支，每个分支的行数、条件字段为空的行和没进任何分支的行都会数出来）；AI 步骤逐行问模型，要抽样复核、另一位确认后它写出的列才能当主键或代码含义用 |
| 本体 | 对象类型（属性、主键、代码列的含义）、关系（检查连上多少行、声明的基数是否成立）、视图（如“有效订单”）、行为（参数、提交条件，经审批才写数据）、派生属性（同一行的公式，或经关系的统计） |
| 确认 | 提出 → 代码检查 → 另一位建设者确认（只有一位建设者时自动放开并记下）；确认时存下数据版本和锚点；新版本上传后重新检查，对不上的回到“需要再看”，读它的东西跟着一起，原因写明是数据变了、定义改了还是上游过时；关系有一个例外：确认时每一行都连上、键没有重复的，只要现在仍然如此就保持已确认，行数变了也一样；一次上传引出的几项可以在一个页面里一起确认 |
| 问答 | 范围只含此人能看的已确认类型；问题提到未确认或需再看的定义，先拒答再说原因，不去问模型；模型看结构、含义和取值不多的列的取值，不看行数据，写出结构化查询，代码执行并核对用到的定义；支持排除某个含义（“没取消的”）、取最高或最低的前 N 个；回答连同定义、确认人和数据版本存下 |
| 使用 | 对象浏览、看板、给智能体的 MCP 工具（用个人令牌，默认只读）、关系图和血缘图（从数据源、上传和管道到数据集，再到对象类型和回答；按“数据变了 / 定义改了 / 上一步过时 / 更上游过时”着色；数据源只给建设者和管理员看，不显示连接信息） |

早期按“一次运行”组织的界面还在 `legacy.html`，见 [docs/LEGACY_SCREEN.md](docs/LEGACY_SCREEN.md)。

## 快速开始

环境要求：Python 3.11+、Node 22+，以及模型 key：DeepSeek（`DEEPSEEK_API_KEY`）或 OpenRouter（`OPENROUTER_API_KEY`，默认用 DeepSeek V4.1 Flash）。上传 PDF 另需本机装有 `pdftotext`（poppler）。

### 一条命令（Mac / Linux）

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc && ./scripts/ontopoc-start.sh
```

装依赖、构建页面、第一次运行时建管理员，然后在 `http://127.0.0.1:8767/` 一个地址提供页面和服务；数据在 `~/.ontopoc/data`。详见 [docs/DEPLOY.md](docs/DEPLOY.md)。

### 方式 A：由 AI 助手安装

将以下内容粘贴至 Claude Code 或 Codex：

```text
请在本机安装并运行 OntoPoc（https://github.com/Longado/ontopoc）：
1. 阅读仓库的 README.md，按"快速开始"操作。
2. 检查 python3 --version ≥ 3.11、node --version ≥ 22；不满足时告诉我安装方法，并暂停后续步骤。
3. 克隆仓库，在仓库根目录执行 python3 -m pip install -e '.[sources]'（[sources] 另装连 PostgreSQL / MySQL 的驱动；系统 Python 不允许直接安装时，先建虚拟环境），在 landing-page 目录执行 npm ci。
4. 向我索取模型 key（DeepSeek 或 OpenRouter），仅写入当前终端的环境变量 DEEPSEEK_API_KEY 或 OPENROUTER_API_KEY，不要写入任何文件。
5. 在仓库根目录先建管理员：PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin（账号和密码由我自己输入）。
6. 再启动服务：PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --origin http://127.0.0.1:5178
7. 另开一个终端启动页面：cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
8. 打开 http://127.0.0.1:5178/ 登录团队应用，上传 examples/company/demo_company.xlsx，告诉我数据集页上看到几张表。
```

### 方式 B：手动安装

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc
python3 -m pip install -e '.[sources]'   # sources：连 PostgreSQL / MySQL 的驱动；系统 Python 不允许时先 python3 -m venv .venv && . .venv/bin/activate
(cd landing-page && npm ci)

# 第一次：在服务所在的机器上建管理员（问账号和密码，至少 12 个字符）
PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin

# 终端 1：服务（端口 8767，数据在 output/ontology-runs/workspace.sqlite；--data-dir 可换目录）
export OPENROUTER_API_KEY=你的key          # 或 DEEPSEEK_API_KEY
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --origin http://127.0.0.1:5178

# 终端 2：页面
cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

访问 `http://127.0.0.1:5178/` 是团队应用；早期界面在 `http://127.0.0.1:5178/legacy.html`。管理员登录后在“用户”里建其他人。未配置 key 时其余功能照常，问答和建模会说明缺 key。修改后端代码后需重启服务，页面检测到服务运行旧代码时会提示。

模型：`DEEPSEEK_API_KEY` 走 DeepSeek 自己的接口；只有 `OPENROUTER_API_KEY` 时走 OpenRouter，默认 `deepseek/deepseek-v4.1-flash`；`EIP_MODEL_API_BASE` 和 `EIP_MODEL_NAME` 可以换成别的 OpenAI 兼容接口和模型名。

页面代码：团队应用在 `landing-page/src/app/`，只用工作空间接口 `/api/workspace/*`；早期界面在 `landing-page/src/legacy/`（入口 `legacy.html`，旧首页文字是 `legacy.html?landing`）。

## 用 MCP / Claude 接入

OntoPoc 的一部分功能封装为 40 个 MCP 工具，也可作为 Claude Code 插件安装。工具与页面共用本机服务：先启动服务，再接入客户端。给外部智能体用个人令牌（`ONTOPOC_TOKEN`）时默认只给 6 个只读工具：读定义、提问、用本体查询直接算、列出未确认项、读派生属性、看每条定义现在是否已确认。

### 作为 Claude Code 插件安装

仓库本身就是一个 Claude Code 插件。安装后可在 Claude Code 里直接建本体、逐项确认；建模、核验和确认记录仍在本机 OntoPoc 服务里完成，使用前需要先启动它（见上文）。

```bash
claude plugin marketplace add Longado/ontopoc
claude plugin install ontopoc@ontopoc
```

新开一个会话后可用两个命令：`/ontopoc:ontopoc-build`（上传文件建本体）与 `/ontopoc:ontopoc-review`（逐项确认）。会话开始时，若本机服务没有运行，插件会提示一行。插件按 `ONTOPOC_PYTHON`、`python3`、`python` 的顺序寻找 Python。

### 接入 Claude Code 或其他 MCP 客户端

这 39 个工具与页面共用同一个本机服务，可在 Claude Code 等客户端中直接调用（在仓库根目录运行）。其中 34 个对应早期界面的运行（建模、查看、问答、确认、导出），5 个对应团队应用：读已确认的定义、提问、用本体查询直接算（[QUERY.md](docs/QUERY.md)）、列出未确认项、读派生属性。团队应用里的上传、写定义和确认还没有 MCP 工具，在页面或 HTTP 接口里做。

```bash
claude mcp add ontopoc -- env ONTOPOC_TOOLSET=all PYTHONPATH=$PWD/src python3 -m ontology_poc_generator.mcp_server
```

工具清单见 [docs/MCP.md](docs/MCP.md)。

## 早期界面：按运行建模

早期按“一次运行”组织的界面还在 `legacy.html`：简介、界面预览、工作原理、快速体验和功能模块见 [docs/LEGACY_SCREEN.md](docs/LEGACY_SCREEN.md)。

## 本体 FAQ

### 什么是 ontology engineering（本体工程）？

在这里，本体工程（ontology engineering）是把业务里的对象、识别方式和对象之间的关系写成可检查的定义。OntoPoc 在试的做法是：从几张业务表或一份文档起草本体草案，由代码对照数据检查，再由人逐项确认后存下来。

### Ontology 和 knowledge graph（知识图谱）有什么不同？

Ontology 先约定「有哪些对象、怎么识别、对象之间可以有什么关系」；knowledge graph 通常还包含具体的实例及其关系。OntoPoc 侧重前者：起草并核对定义，并在本次上传的数据上做检查与问答。它不是知识图谱平台，也不提供持久实例库或线上对象查询。

### 这和自动生成本体有什么不同？

最近的一些工作让语言模型承担从文本建本体或图谱的大部分工作：AutoOntic（[arXiv 2611.15467](https://arxiv.org/abs/2611.15467)）归纳类型、层级和关系约束，Causals（[arXiv 2611.16267](https://arxiv.org/abs/2611.16267)）是从新闻建的图谱。两篇都写明了没测的部分：AutoOntic 的评测“不直接衡量抽取的精确率”，Causals 的发布版“没有有代表性的语义准确率估计”。OntoPoc 做的是起草之后的一步，主要面向表：在团队应用里，每个定义由代码对照数据检查，由一位具名的人确认，数据变了就回到“需要再看”。那里模型也可以起草定义，但在通过检查并被确认之前，问答和智能体都不会用它；在那之前，看板只对建设者和管理员显示依赖它的数，标灰并写明原因，查看者看不到。（早期按运行组织的界面要宽松一些：还没有人判断过的内容会保留下来。）

### 这和 semantic layer（语义层）是什么关系？

语义层常指在数仓或指标平台上，定义业务含义（对象、指标、口径）供查询复用。OntoPoc 做的是更靠前的一步：第一次拿到客户表或文档时，整理对象、识别字段、关系，以及需要和客户确认的口径；可导出对象表单、编排需求单和 Turtle（OWL / SHACL），交给后续的数据平台或管道工作。是否导入某个具体平台，目前尚未实测。

### 什么是 ontology MCP？可以怎么用？

这里的 ontology MCP 指通过 MCP 工具调用本体相关功能。OntoPoc 把页面上的部分能力做成 MCP 工具（共 39 个，其中 5 个给团队应用：读定义、提问、用本体查询直接算、列出未确认项、读派生属性），供 Claude Code、Claude Desktop、Cursor 等支持 MCP 的客户端调用。工具走本机 stdio，调用的是本机正在运行的建模服务。Claude Code 也可直接装仓库插件后使用 `/ontopoc:ontopoc-build` 与 `/ontopoc:ontopoc-review`。接法见[用 MCP / Claude 接入](#用-mcp--claude-接入)，工具清单见 [docs/MCP.md](docs/MCP.md)。

### OntoPoc 现在适合谁用？

团队应用设想给一个数据团队用：建设者从数据建定义、互相确认，查看者只问问题、看看板。早期界面设想给数据平台的实施顾问：第一次拿到客户数据时梳理业务对象及其关系。两者都还没有作者以外的用户独立用过；页面仅在 macOS 上实际用过。更多边界见[已知问题](docs/KNOWN_ISSUES.md)。

## 隐私

- 上传的文件及全部结果仅保存在本机 `output/ontology-runs/` 目录。
- 团队应用里，模型看对象类型、属性的名字和类型、已确认的代码含义、关系和派生属性的说明，以及取值种类不多的列（如城市、等级）的全部取值；主键列和管理员标为“不发取值”的列不发取值。不发行数据。
- 早期界面发送给模型（DeepSeek 或 OpenRouter 上的模型）的内容仅包括：建模目的；每张表的行数、各列字段名、至多 3 个示例值、代码数出的计数（有值个数、不同值个数、是否各不相同）、每张表每行都不同的列或两列组合、可能的连接（包括指向本表的）；像类别那样反复出现的列的全部取值；生成问题时，取值不超过 12 种的列的全部取值，以及你在问答里输入的问题原文；点“起草”字段释义时，各字段的类型和最长长度；点“找出可能的对应”时，只用一个字段识别、取值 2–200 个的对象的全部识别值及各值出现的行数；文档则为正文，每次至多 12 段。建模时将发送的内容，上传前可在页面逐列查看。
- 每次模型调用在本机 `output/ontology-runs/model_calls.jsonl` 记录一行（Agent、耗时、成功与否），不记录调用内容。
- 服务仅接受本机请求。

## 已知问题

见 [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)。

## 参与共建

**业务人员能否自行读懂、修正本体，并在后续工作中持续使用？**

| 方向 | 可贡献的内容 |
|---|---|
| 用户研究 | 邀请一位非作者的顾问独立完成从上传到导出纪要的全流程，记录受阻环节 |
| 数据质量 | 规则发现目前仅支持"必填"与"日期先后"两类，取值范围、非负等规则需先在真实数据上验证定义 |
| 平台对接 | 在具体数据平台上实测批量导入，补充关系表导出 |
| 提示词评测 | 从本机运行结果中选取已确认样本作为标注集，实现新旧提示词的一键对比 |
| 跨平台 | 在 Windows、Linux 上完整运行，并以 issue 形式反馈问题 |

欢迎提交 issue 或 pull request。开发前请先阅读[开发规范](docs/DEVELOPMENT_GUARDRAILS.md)。

### 登录与账号

服务默认要登录，没有默认账号和默认密码。建管理员、角色、令牌、两人确认和给团队部署，见 [docs/ACCOUNTS.md](docs/ACCOUNTS.md)。

## 开发

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q      # 后端测试（约 2000 个；先 pip install -e ".[check,sources]"，否则 TTL 校验等会跳过）
npm --prefix landing-page run test:unit                       # 前端测试（约 530 个）
PYTHONPATH=src:. python3 scripts/real_model_check.py --out /tmp/check   # 真实模型对照 SQL 的检查（要模型 key；只有错数才算失败）
PYTHONPATH=src:. python3 scripts/run_company_ontology.py --file examples/company/demo_company.xlsx --output output/demo-run.json
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --data-dir /tmp/ontopoc-trial   # 试跑用另一个数据目录，不动已有运行
PYTHONPATH=src:. python3 scripts/make_demo_company.py         # 重新生成合成示例工作簿
```

| 文档 | 内容 |
|---|---|
| [docs/PRODUCT.md](docs/PRODUCT.md) | 开发方向与边界 |
| [docs/PLAYGROUND_INTERNALIZATION.md](docs/PLAYGROUND_INTERNALIZATION.md) | 本体库来源、RDF/XML 导入边界与后续轮次 |
| [docs/AGENTS.md](docs/AGENTS.md) | 6 个 Agent 的定义与调用记录 |
| [docs/MCP.md](docs/MCP.md) | MCP 工具清单 |
| [docs/PLATFORM_FORM_REFERENCE.md](docs/PLATFORM_FORM_REFERENCE.md) | 数据平台对象表单对照 |
| [docs/PRD_ITERATION_9.md](docs/PRD_ITERATION_9.md) | 最近一份迭代计划（第 9 轮，闭环）；之后各轮的改动见已合并 PR 的说明 |
| [docs/DEVELOPMENT_GUARDRAILS.md](docs/DEVELOPMENT_GUARDRAILS.md) | 开发红线与待触发的方向 |

## 许可证

[AGPL-3.0](LICENSE) © Yutai Lin。v0.2.0 及更早的版本仍按 MIT 发布；需要商业许可的，见 [NOTICE.md](NOTICE.md)。

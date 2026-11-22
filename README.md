<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
    <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc" width="360">
  </picture>
</p>

<h1 align="center">OntoPoc</h1>
<p align="center"><strong>团队数据和回答问题的 AI 之间的确认关口：AI 只按具名同事对着当前数据确认过的定义回答；没确认的，就拒答并说出谁能确认。</strong></p>
<p align="center">Ontology tool for teams and MCP / Claude：数据 → 定义 → 检查 → 确认 → 受门控的问答、看板和智能体。</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL--3.0-blue" alt="AGPL-3.0"></a>
  <img src="https://img.shields.io/badge/tested%20on-macOS-black" alt="tested on macOS">
  <img src="https://img.shields.io/badge/Python-3.11%2B-green" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Node-22%2B-green" alt="Node 22+">
  <img src="https://img.shields.io/badge/status-Alpha-orange" alt="Alpha">
</p>

<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="https://longado.github.io/ontopoc/zh/">Docs</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="docs/pilot/FIRST_DEFINITION.md">动手试一遍</a> ·
  <a href="#给智能体用mcp--claude">MCP / Claude</a> ·
  <a href="#本体-faq">本体 FAQ</a> ·
  <a href="#参与共建">参与共建</a>
</p>

<p align="center"><sub>Ontology tool for MCP / Claude · Docs: <a href="https://longado.github.io/ontopoc/">longado.github.io/ontopoc</a> · Follow on X: <a href="https://x.com/linyutai120479">@linyutai120479</a></sub></p>

<p align="center">
  <img src="docs/media/ontopoc-hero.gif" alt="OntoPoc：业务表格变成等人确认的定义" width="960">
</p>
<p align="center"><sub>功能主题插画 · <a href="docs/media/ontopoc-poster.png">静态版</a> · <a href="docs/media/ontopoc-motion.mp4">MP4</a></sub></p>

OntoPoc is an ontology tool for a team's own data: the team writes down what its tables mean (object types, keys, code meanings, relations, views), code checks each definition against every row, a second named person confirms it on a given data version, and Q&A, boards and AI agents over MCP answer only from what was confirmed. It is not a knowledge-graph platform; it is the confirmed part of a semantic layer.

团队把表格的含义写下来：对象类型和主键、代码列每个取值是什么意思（例如状态码 2 = 已取消）、关系、视图（例如“有效订单”）、派生属性。这就是团队的本体（ontology），也就是语义层里“这个数怎么算”的那一部分。每个定义由代码在全部行上检查，再由另一位具名同事对着某一版数据确认。问答、看板和通过 MCP 接进来的 AI 只用确认过的定义；数据或定义一变，靠它的东西回到“需再看”，用到它的问题拒答，说出是哪一项、谁能确认。OntoPoc 还在开发中，还没有作者以外的用户。

## 它会怎么拒答

三种结果，都在仓库自带的示例数据上（150 张订单，状态码 0–5），[演示站](https://35-229-236-140.sslip.io/)（临时地址）用的也是这份数据，访客只读：

| 你问 | OntoPoc 答 | 为什么 |
|---|---|---|
| “有效订单的总金额是多少？” | **119,810**，旁边写着按什么算的：视图“有效订单”（已付款、已发货、已送达），谁确认的，基于订单第 1 版 | 用到的定义都确认过 |
| 问题点名了一个还没人确认的定义 | 在问模型之前就挡下，说出是哪个定义、谁能确认 | 提出不等于确认。能看到这个定义的人会得知名字和谁能确认；查看者只读已确认的定义，从没确认过的定义不会被告知名字，已确认、正在等再确认的只被告知回答在等确认 |
| 上传 `orders_update.csv`（出现新代码 6，没人写过含义）之后再问同一题 | 拒答：“有效订单”需再看；看板上显示它在等谁、上次的数 | 确认之后数据变了 |

回答算的是全部行时，旁边还给出每个已确认视图各自的数；回答只算一个已确认视图时，旁边还给出全部行的数。上面那个数算哪些行，和以前一样决定。

演示站上，访客能看到第一种回答，和一次第三种拒答：类型 Customer 确认过一次、现在在等第二次确认，问题里写出它的名字 Customer（不分大小写和单复数，作为一个整词，例如“按 Customer 城市看有效订单金额”）时，会在问模型之前拒答，访客只会被告知回答在等确认；只写“客户”不算写出它的名字，这样的问题照常交给模型。

金额列直接加总是 162,960。算术没错，但它不是营收：已取消、已退款的订单也带着金额。关口就是为这个差额准备的。

## 一个定义怎么被确认

1. **提出。** 建设者写定义，让模型从数据集建议一个，或者导入 dbt `manifest.json` 里的测试（建议和导入都只是提议）。
2. **代码在全部行上检查。** 主键唯一、没有空值；关系连得上（连不上的有多少也写出来）；每个代码都有含义；对象类型属性上的每条值规则都成立（不能为空；大于、至少、小于、最多某个数，或在两个数之间；是写了含义的代码之一；一个日期不早于另一个），违反的行数出来，最多 20 行按主键列出。数据违反的规则可以先提出，但要等没有一行违反，类型才能确认。主键检查查了 0 行不算通过（关系检查还没区分这一点）。
3. **另一位建设者确认。** 提出的人不能自己确认；只有一位建设者时规则自动放开，日志里写明。确认时记下是谁、什么时候、哪一版数据。
4. **开始被使用。** 问答、看板、智能体都能用它，每个数旁边写着它按哪条口径算。
5. **数据一动就退回。** 新上传或新拉取会重新检查；对不上的，连同读它的东西一起回到“需再看”，原因写明是数据变了、定义改了，还是上游过时。待确认队列把它带回第 3 步。

两个人、大约 40 分钟走一遍：[docs/pilot/FIRST_DEFINITION.md](docs/pilot/FIRST_DEFINITION.md)（英文）。

## 快速开始

环境要求：Python 3.11+、Node 22+。模型 key（DeepSeek 的 `DEEPSEEK_API_KEY` 或 OpenRouter 的 `OPENROUTER_API_KEY`）可选：没有 key 时，问答和建议会说明缺 key，其余照常。

### 一条命令（Mac / Linux）

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc && ./scripts/ontopoc-start.sh
```

装依赖、构建页面、第一次运行时建管理员，然后在 `http://127.0.0.1:8767/` 一个地址提供页面和服务；数据在 `~/.ontopoc/data`。给团队用、走 HTTPS 见 [docs/DEPLOY.md](docs/DEPLOY.md)。想和团队试两周，用[试点包](docs/pilot/README.md)（中文一页纸：[QUICKSTART.zh.md](docs/pilot/QUICKSTART.zh.md)）。

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
8. 打开 http://127.0.0.1:5178/ 登录，上传 docs/pilot/sample/orders.csv 和 customers.csv，告诉我两个数据集各有多少行。
```

### 方式 B：手动安装

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc
python3 -m pip install -e '.[sources]'   # sources：连 PostgreSQL / MySQL 的驱动；系统 Python 不允许时先 python3 -m venv .venv && . .venv/bin/activate
(cd landing-page && npm ci)

# 第一次：在服务所在的机器上建管理员（问账号和密码，至少 12 个字符）
PYTHONPATH=src python3 -m ontology_poc_generator.accounts create-admin

# 终端 1：服务（端口 8767，数据在 output/ontology-runs/workspace.sqlite；--data-dir 可换目录）
export OPENROUTER_API_KEY=你的key          # 或 DEEPSEEK_API_KEY；可选
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --origin http://127.0.0.1:5178

# 终端 2：页面
cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

管理员登录后在“用户”里建其他人。修改后端代码后需重启服务，页面检测到服务运行旧代码时会提示。

模型：`DEEPSEEK_API_KEY` 走 DeepSeek 自己的接口；只有 `OPENROUTER_API_KEY` 时走 OpenRouter，默认 `deepseek/deepseek-v4.1-flash`；`EIP_MODEL_API_BASE` 和 `EIP_MODEL_NAME` 可以换成别的 OpenAI 兼容接口和模型名。

## 给智能体用（MCP / Claude）

外部智能体以某位同事的身份接进来：管理员在“AI 工具接入”页给这个人发一个令牌。设了 `ONTOPOC_TOOLSET=read`（下面的命令都设了），或者令牌是只读的（那一页默认给只读），智能体就只拿到 6 个只读的 MCP 工具，权限按这个人算：

| 工具 | 做什么 |
|---|---|
| `describe_definitions` | 已确认的对象类型、属性、代码含义、关系、视图、派生属性，以及拒答规则 |
| `ontopoc_query` | 直接写本体查询算一个数（[QUERY.md](docs/QUERY.md)），不经模型 |
| `ask` | 写不出查询时用一句话问：模型写查询，代码算 |
| `list_unconfirmed` | 还不能用的定义，以及原因 |
| `read_derived_property` | 读一个已确认的派生属性的值 |
| `definition_standing` | 每条定义现在是不是已确认、谁确认的、在哪个数据版本上；没确认的写明原因和谁能确认。同一份也在 `GET /api/workspace/agent/standing`，可下载 CSV |

它会拒绝的：用到了没确认、需再看、或这个人看不到的定义。拒答原样转给智能体，带着原因，不给猜出来的数。这 6 个工具不能上传、写定义或确认。范围是“全部”的令牌（个人在自己账号页建令牌时的默认值）如果不设 `ONTOPOC_TOOLSET=read`，还会带出早期界面的 34 个运行类工具，能在那边上传文件、建模和确认；所以要设上。先启动服务，再在仓库根目录：

```bash
claude mcp add ontopoc -- env ONTOPOC_TOKEN=<你的令牌> ONTOPOC_TOOLSET=read PYTHONPATH=$PWD/src python3 -m ontology_poc_generator.mcp_server
```

“AI 工具接入”页也给出填好服务地址的 JSON，供 Claude Desktop、Cursor 等 MCP 客户端粘贴；粘贴时在 `env` 里加上 `"ONTOPOC_TOOLSET": "read"`。工具清单见 [docs/MCP.md](docs/MCP.md)。那一页还能下载技能包（zip），它是已确认定义的一份快照，之后数据变了也不会拒答，所以优先用 MCP。

**Claude Code 插件。** 仓库本身也是 Claude Code 插件（`claude plugin marketplace add Longado/ontopoc`，再 `claude plugin install ontopoc@ontopoc`）。它的两个命令 `/ontopoc:ontopoc-build`、`/ontopoc:ontopoc-review` 目前走的是早期按运行建模的界面，不经过团队应用的确认关口，见 [docs/LEGACY_SCREEN.md](docs/LEGACY_SCREEN.md)。

## 里面有什么，不做什么

| 部分 | 做什么 |
|---|---|
| 账号与权限 | 本机账号，管理员、建设者、查看者三种角色，服务端会话。查看者只看已确认的定义。管理员可按对象类型限定人、按行限定人（只有允许清单）、隐藏列、让某列的值不发给模型 |
| 数据 | 上传 CSV / Excel，按主键更新或覆盖，每次一个新版本，导入时核对行数。只读连接 PostgreSQL、MySQL：拉取是把表**复制**成一个新版本，每次最多 50 万行、约 200 MB，超过就拒绝，不会截断。只支持 PostgreSQL 和 MySQL；在你的数据库里就地检查还没有做。调度按小时、每天、每周拉取或运行管道 |
| 定义 | 对象类型（主键、属性、代码列的含义、属性上的值规则：每个类型最多 20 条，每条只管这个类型的一个属性）、关系（连上多少行、声明的基数是否成立）、视图、派生属性（同一行的公式，或经关系的统计） |
| 确认 | 提出 → 代码检查 → 另一位建设者确认，存下数据版本和锚点。数据或定义一变，对不上的回到“需再看”，能确认它的人和上次确认它的人在“消息”里各收到一条。关系有一个例外：确认时每一行都连上、键没有重复的，只要现在仍然如此就保持已确认，行数变了也一样。一次上传动到的几项可以在一个页面里一起确认 |
| 回答 | 问答：问题点名了未确认或需再看的定义，先拒答再说原因，不去问模型；模型看结构、含义和取值不多的列的取值，不看行数据，写出结构化查询，代码执行并核对用到的定义。OntoPoc Query 不经模型直接算。看板过同一道门 |
| 周边 | 轻管道（过滤、连接、分组、去重、计算列、合并、拆分），血缘图和关系图（按退回原因着色），对象浏览，中英两种界面 |

不做的：重编排、大规模数据、对你的数据库现查、图表种类上的竞争。“行为”（审批后写数据）和管道里的 AI 步骤还在，但不在主路径上。早期按运行建模的界面在 `legacy.html`（见最后一行）。

## 隐私

- 上传的文件、拉来的表和全部结果只存在运行服务的这台机器上。
- 模型看对象类型、属性的名字和类型、已确认的代码含义、关系和派生属性的说明，以及取值种类不多的列（如城市、等级）的全部取值；主键列和管理员标为“不发取值”的列不发取值。不发行数据。
- 每次模型调用在 `model_calls.jsonl` 记录一行（哪个 Agent、耗时、成功与否），不记录调用内容。
- 早期界面发给模型的内容见 [docs/LEGACY_SCREEN.md](docs/LEGACY_SCREEN.md#发给模型的内容)。

## 已知问题

见 [docs/KNOWN_ISSUES.md](docs/KNOWN_ISSUES.md)。

## 本体 FAQ

### 什么是 ontology engineering（本体工程）？

在这里，本体工程是把业务里的对象、识别方式、代码含义、算哪些行（视图）和对象之间的关系，写成可以检查的定义。在 OntoPoc 里，人或模型提出一个定义，代码对照数据检查，再由另一个人确认。

### Ontology 和 knowledge graph（知识图谱）有什么不同？

Ontology 先约定「有哪些对象、怎么识别、对象之间可以有什么关系」；knowledge graph 通常还包含具体的实例及其关系。OntoPoc 侧重前者，用的是复制进它自己工作区的数据。它不是知识图谱平台，也不提供持久的实例库。

### 这和自动生成本体有什么不同？

最近的一些工作让语言模型承担从文本建本体或图谱的大部分工作：AutoOntic（[arXiv 2611.15467](https://arxiv.org/abs/2611.15467)）归纳类型、层级和关系约束，Causals（[arXiv 2611.16267](https://arxiv.org/abs/2611.16267)）是从新闻建的图谱。两篇都写明了没测的部分：AutoOntic 的评测“不直接衡量抽取的精确率”，Causals 的发布版“没有有代表性的语义准确率估计”。OntoPoc 做的是起草之后的一步，主要面向表：每个定义由代码对照数据检查，由一位具名的人确认，数据变了就回到“需再看”。模型也可以起草定义，但在通过检查并被确认之前，问答和智能体都不会用它；在那之前，看板只对建设者和管理员显示依赖它的数，标灰并写明原因，查看者看不到。

### 这和 semantic layer（语义层）是什么关系？

你们的指标可能已经在数仓的语义层里定义好了。谁签过字？底下的数据变了，谁会知道？OntoPoc 管的就是这一段：每个定义带着确认人和数据版本，数据一动就回到“需再看”，在有人重新确认之前，AI 不会拿它回答。它用自己复制的一份数据。已经用 dbt 的，可以在对象类型页上传 `manifest.json`：OntoPoc 读其中的模型测试（unique、not_null、relationships、accepted_values），提出对象类型和关系，一次最多 50 个，写入前先给出预览；每一个仍要另一位建设者对着数据确认。复合主键、dbt 的 constraints、metrics、语义层和 dbt Cloud 都不读，manifest 之后的改动也不会跟着同步，导入本身不确认任何东西。目前也还不能导出到某个具体的语义层。

### 什么是 ontology MCP？可以怎么用？

这里的 ontology MCP 指智能体通过 MCP 工具读一个团队已确认的本体。设了 `ONTOPOC_TOOLSET=read` 或用只读令牌时，OntoPoc 的 MCP 服务给智能体 6 个只读工具（读定义、提问、用本体查询直接算、列出未确认项、读派生属性、看每条定义现在是否已确认），按个人令牌的权限算，供 Claude Code、Claude Desktop、Cursor 等客户端通过本机 stdio 调用。接法见[给智能体用](#给智能体用mcp--claude)，清单见 [docs/MCP.md](docs/MCP.md)。

### OntoPoc 现在适合谁用？

想让 AI 回答自家表格问题、又希望它答不准时宁可拒答的小数据团队（三到八个人，运营、财务、数据）。建设者写定义、互相确认，查看者问问题、看看板。还没有作者以外的用户独立用过；页面只在 macOS 上实际用过。

## 参与共建

**团队的 AI 是不是在该拒答的时候拒答，而且只在那时候拒答？**

| 方向 | 可贡献的内容 |
|---|---|
| 试点 | 和一个小团队跑一遍[试点包](docs/pilot/README.md)，把提问记录发回来：答对、答错、拒答，以及每次拒答有没有道理 |
| 检查 | 找一个能通过检查、在像样的数据上却仍然是错的定义，连数据一起提 issue |
| 智能体 | 用只读令牌接一个 MCP 客户端，说说拒答规则哪里让它看不明白 |
| 提示词评测 | 从已认可的回答里选出标注样本，实现新旧提示词的一键对比 |
| 跨平台 | 在 Windows、Linux 上完整运行，并以 issue 形式反馈问题 |

欢迎提交 issue 或 pull request。开发前请先阅读[开发规范](docs/DEVELOPMENT_GUARDRAILS.md)。登录、角色、令牌和两人确认见 [docs/ACCOUNTS.md](docs/ACCOUNTS.md)；服务没有默认账号和默认密码。

## 开发

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q      # 后端测试（2026-11-22 共 2,414 个；先 pip install -e ".[check,sources]"，否则 TTL 校验等会跳过）
npm --prefix landing-page run test:unit                       # 前端测试（2026-11-22 共 801 个）
PYTHONPATH=src:. python3 scripts/real_model_check.py --out /tmp/check   # 真实模型对照 SQL 的检查（要模型 key；只有错数才算失败）
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server --data-dir /tmp/ontopoc-trial   # 试跑用另一个数据目录
```

页面代码：团队应用在 `landing-page/src/app/`，只用 `/api/workspace/*`；早期界面在 `landing-page/src/legacy/`。

| 文档 | 内容 |
|---|---|
| [docs/PRODUCT.md](docs/PRODUCT.md) | OntoPoc 做什么，留什么、不做什么 |
| [docs/QUERY.md](docs/QUERY.md) | OntoPoc Query |
| [docs/MCP.md](docs/MCP.md) | MCP 工具清单 |
| [docs/AGENTS.md](docs/AGENTS.md) | 每一次模型调用的定义卡与调用记录 |
| [docs/DEVELOPMENT_GUARDRAILS.md](docs/DEVELOPMENT_GUARDRAILS.md) | 开发红线与待触发的方向 |

## 许可证

[AGPL-3.0](LICENSE) © Yutai Lin。v0.2.0 及更早的版本仍按 MIT 发布；需要商业许可的，见 [NOTICE.md](NOTICE.md)。

---

早期按“一次运行”组织的界面（从几张表或一份文档起草本体、口径卡、对象表单和 Turtle 导出；在那里上传 PDF 另需本机装 poppler 的 `pdftotext`）还在 `legacy.html`：见 [docs/LEGACY_SCREEN.md](docs/LEGACY_SCREEN.md)。

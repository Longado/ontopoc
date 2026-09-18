<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
    <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc" width="360">
  </picture>
</p>

<h1 align="center">OntoPoc</h1>
<p align="center"><strong>把客户的业务表交给它，几分钟后拿到一份本体草案，以及每一条靠不靠得住的证据。</strong></p>
<p align="center">给做数据平台交付的实施顾问：第一次拿到客户数据、要弄清"业务里有哪些东西、怎么连"的时候用。</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue" alt="MIT"></a>
  <img src="https://img.shields.io/badge/tested%20on-macOS-black" alt="tested on macOS">
  <img src="https://img.shields.io/badge/Python-3.11%2B-green" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Node-22%2B-green" alt="Node 22+">
  <img src="https://img.shields.io/badge/status-Alpha-orange" alt="Alpha">
</p>

<p align="center">
  <a href="README.en.md">English</a> ·
  <a href="#快速开始">快速开始</a> ·
  <a href="#可以试试这些">可以试试这些</a> ·
  <a href="#一起做">一起做</a>
</p>

别的做法是让大模型一口气画出本体，对不对全凭感觉；OntoPoc 让模型只提议，每一条都由代码拿数据逐行核一遍，再交给你拍板。

**整行数据不出本机** · **每个数字都是代码算的** · **不改你的数据**

## 是什么

上传几张业务表（Excel、CSV）或一份流程文档，OntoPoc 起草一份本体：业务里有哪些对象、每个对象按什么识别、对象之间怎么关联。然后代码拿每一行去核：字段在不在、识别字段有没有值、关系在数据里连不连得上；再做一轮数据体检，用数据回答业务问题。你逐项判断对不对，判断被存下来，同一份文件或它的新版本下次上传，就从你的判断开始。

最后可以按 DIP 平台的对象表单导出，或者把每个功能当成 MCP 工具交给别的 agent 调。

> **早期版本。** 验证用的全是公开数据和合成数据（芝加哥市政合同、Northwind、BART 地铁、台湾公司登记、CMS 医院等），还没有一个作者以外的人独立用完一遍。只在 macOS 上跑过。DIP 的批量导入契约没实测过。详见[已知问题](#已知问题)。

## 看一眼

<p align="center"><img src="docs/images/readme-objects.png" alt="本体管理：每个业务对象一张卡片" width="880"></p>
<p align="center"><sub>本体管理：示例工作簿建出的 4 个对象，顶部是体检、问答、稳定性的状态。</sub></p>

<p align="center"><img src="docs/images/readme-instances.png" alt="实例图谱：从一个客户展开它的订单和产品" width="880"></p>
<p align="center"><sub>实例图谱：从客户 KH001 展开它的订单，再从订单展开产品；右侧是选中订单的字段原值。</sub></p>

<p align="center"><img src="docs/images/readme-ask.png" alt="智能问答：答案由代码在数据上算出" width="880"></p>
<p align="center"><sub>智能问答：模型把问题写成查询，数字由代码在上传的数据上算，并写明读到了几个值。</sub></p>

<p align="center"><img src="docs/images/readme-rules.png" alt="规则：从数据里找到的规则，采纳后每次重跑都检查" width="880"></p>
<p align="center"><sub>数据体检里的规则：代码从数据里找出候选规则，采纳后每次重跑都会检查。</sub></p>

截图都来自仓库自带的合成示例 `examples/company/demo_company.xlsx`，由无头浏览器离屏渲染。

## 它怎么做

| 你…… | 它会…… |
|---|---|
| 上传表格，写一句想弄清的问题 | 模型只看每列的字段名和最多 3 个示例值，提出对象、识别字段和关系；代码按 17 类错误核验，错了退回重做，最多 3 版 |
| 等建模完成 | 同一份文件同时建 3 次，标出 3 次不一致的地方（那是模型拿不准、该你决定的地方） |
| 打开"数据体检" | 代码逐行算 7 项检查，比如同一个编号的信息打不打架、每张上传的表是否都用上了 |
| 在"智能问答"里提问 | 模型把问题写成结构化查询，代码在数据上算答案；答不了就写明是本体缺了、数据没有，还是问法不支持。每次出 6 道题 |
| 逐项判对错、改名、补漏 | 存成这份文件的参考本体；下次上传自动对照、预填 |
| 把几道题固定为验收问题（最多 3 道） | 以后每次重跑都用同一个查询再算一次，只告诉你哪道变了 |
| 采纳数据里找到的规则 | 以后每次重跑都检查，列出违反规则的对象 |
| 客户发来新版文件，你说"是新版本" | 上次的确认、验收问题、规则接着用，并给出每个对象多了几个、少了几个 |
| 点"起草"填 DIP 表单 | 一次模型调用，起草中文名、描述、展示字段；你改过的不会被再次起草覆盖 |
| 点右上角"⤓ DIP" | 每个对象一张 CSV，列与 DIP 对象表单一致 |

模型只做判断，循环和计算都在代码里；每个用户动作最多 3 次模型调用。一共 5 个 Agent，定义卡在 [docs/AGENTS.md](docs/AGENTS.md)。

## 可以试试这些

装好后（见[快速开始](#快速开始)），用仓库自带的合成示例：

| 试试 | 你会看到 |
|---|---|
| 不启动建模服务，点"打开示例数据表" | 一份内置的结果：4 个对象、3 条关系 |
| 上传 `examples/company/demo_company.xlsx`，写"哪些客户的售后问题最多？" | 半分钟到一分钟后出现客户、产品、订单、售后工单 4 张卡片；数据体检 5 / 7，没通过的两项正是示例里故意埋的问题 |
| 智能问答里问"每个客户的订单总金额是多少？" | 按客户排序的合计，第一名 241,420，读到 160 个值 |
| 本体关系 → 实例图谱，选一个客户 | 这个客户和它的订单连成一张图，点订单再展开产品 |
| 右上角"⤓ DIP" | 一个压缩包：4 张对象表单 CSV 和一份导入前说明 |

## 快速开始

需要 Python 3.11+、Node 22+，以及一个 DeepSeek API key。

### 方式 A：让你的 AI 帮你装

把下面这段贴进 Claude Code 或 Codex：

```text
帮我在本机装好并跑起 OntoPoc（https://github.com/Longado/ontopoc）：
1. 先读仓库的 README.md，照"快速开始"做。
2. 检查 python3 --version ≥ 3.11、node --version ≥ 22，不满足就告诉我怎么装，先别往下做。
3. 克隆仓库，在 landing-page 里 npm ci。
4. 问我要 DeepSeek API key，只放进当前终端的环境变量 DEEPSEEK_API_KEY，不要写进任何文件。
5. 在仓库根目录启动建模服务：PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server
6. 另开一个终端启动页面：cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
7. 打开 http://127.0.0.1:5178，上传 examples/company/demo_company.xlsx 试一次，告诉我数据体检通过了几项。
```

### 方式 B：自己装

```bash
git clone https://github.com/Longado/ontopoc.git && cd ontopoc
(cd landing-page && npm ci)

# 终端 1：建模服务（端口 8767，结果存在 output/ontology-runs/）
export DEEPSEEK_API_KEY=你的key
PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server

# 终端 2：页面
cd landing-page && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

打开 `http://127.0.0.1:5178`。没有 key 也能打开内置示例；改了后端代码要重启建模服务，页面发现服务在跑旧代码会提示。

### 接到 Claude Code 或别的 MCP 客户端

页面上的每个功能都是一个标准 MCP 工具（stdio，25 个），调用的是同一个本机服务：

```bash
claude mcp add ontopoc -- env PYTHONPATH=$PWD/src python3 -m ontology_poc_generator.mcp_server
```

工具清单见 [docs/MCP.md](docs/MCP.md)。

## 功能

| 模块 | 里面有什么 |
|---|---|
| 数据接入 | 每张上传的表：行数、跳过的标题行、每列类型、长度、填充比例；表之间没连上时，提示能把它们连起来的列 |
| 本体管理 | 对象卡片（搜索、按判断筛选、卡片 / 列表）；对象详情：概览、属性（即 DIP 表单）、数据行（分页、下载 CSV）、确认；逐项确认、稳定性、和上次比、新版本、建模记录 |
| 本体关系 | 自动布局的关系图（可拖、可缩放）、实例图谱、关系列表；代码在数据里看到而本体里没有的关系画成虚线建议 |
| 智能问答 | 提问、验收问题、模型出的题（按能不能答筛选） |
| 数据体检 | 7 项体检、规则、对照标准本体 |

还有一个示例场景：用同一套方法研判车辆召回范围（NHTSA 公开数据），入口在侧边栏"更多示例"，说明见 [docs/RECALL_EXAMPLE.md](docs/RECALL_EXAMPLE.md)。OntoPoc 与 NHTSA 及任何车企无关联，候选结论不构成缺陷认定。

## 隐私

- 上传的文件和所有结果只存在本机的 `output/ontology-runs/`。
- 发给模型（DeepSeek）的只有：每列字段名和最多 3 个示例值；出题时，取值不超过 12 种的列的全部取值；文档则是正文，每次最多 12 段。上传页可以在发送前逐列看清楚。
- 每次模型调用在本机 `output/ontology-runs/model_calls.jsonl` 记一行（哪个 Agent、耗时、成败），不记内容。
- 页面只接受本机请求。

## 已知问题

- **模型每次搭得不一样。** 同一份文件建 3 次常有出入，比如 Northwind 那次 8 个对象里只有 4 个 3 次都有。页面把不一致的地方标出来，由你决定。
- **新版本对比会遇到模型换识别方式。** 芝加哥合同有一次从"合同号 + 修订号"换成只用合同号，这时只能比数量，不能逐个比，页面会写明"识别方式变了"。
- **代码推断关系只找回一部分。** 在 17 份保存过的运行（公开数据和合成数据）上逐条拿掉关系再找，33 条找回 24 条；完整的本体上没有报过假关系。
- **查询还不支持**：按数值条件筛选、限定时间段、一道题给两个数、"哪些东西常一起出现"。遇到会照实说不支持。
- **DIP 批量导入没实测。** 导出的表单列是按 DIP 界面核对过的，导入格式、主键规则、关系表达都还没和平台确认，所以关系表没导出。
- **只在 macOS 上跑过。** Windows、Linux 没测。

## 一起做

**这份本体能不能让业务方的人自己看懂、改对，并且下次还接得上？**

| 你喜欢…… | 可以贡献 |
|---|---|
| 做用户研究 | 找一位不是作者的顾问，不插手地从上传用到下载纪要，记下卡在哪 |
| 数据质量 | 规则发现目前只有"必填"和"日期先后"两种，取值范围、不为负等要先在真数据上跑出定义 |
| 数据平台对接 | 实测 DIP 的批量导入契约，补上关系表导出 |
| 提示词与评测 | 从本机运行里挑一批认可的结果做标注样本，一条命令比较新旧提示词 |
| 跨平台 | 在 Windows、Linux 上跑一遍，把卡住的地方写进 issue |

欢迎提 issue 或 pull request。开发前先读[开发护栏](docs/DEVELOPMENT_GUARDRAILS.md)。

## 开发

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -q      # 后端测试（487 个）
npm --prefix landing-page run test:unit                       # 页面测试（191 个）
PYTHONPATH=src:. python3 scripts/run_company_ontology.py --file examples/company/demo_company.xlsx --output output/demo-run.json
PYTHONPATH=src:. python3 scripts/make_demo_company.py         # 重新生成合成示例工作簿
```

| 文档 | 写什么 |
|---|---|
| [docs/PRODUCT.md](docs/PRODUCT.md) | 产品是什么、站在哪几层 |
| [docs/AGENTS.md](docs/AGENTS.md) | 5 个 Agent 的定义卡、调用记录 |
| [docs/MCP.md](docs/MCP.md) | 25 个 MCP 工具 |
| [docs/DIP_INTERFACE_REFERENCE.md](docs/DIP_INTERFACE_REFERENCE.md) | 对照 DIP 平台的表单与界面 |
| [docs/PRD_ITERATION_7.md](docs/PRD_ITERATION_7.md) | 最近一轮的计划与执行记录 |
| [docs/DEVELOPMENT_GUARDRAILS.md](docs/DEVELOPMENT_GUARDRAILS.md) | 红线，以及等触发再做的方向 |

## 许可证

[MIT](LICENSE) © Yutai Lin

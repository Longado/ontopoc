# OntoPoc 的 MCP 工具

OntoPoc 是团队数据和回答问题的 AI 之间的确认关口。给外部智能体的是 6 个只读工具（令牌是只读的，或设了 `ONTOPOC_TOOLSET=read`）：智能体以令牌主人的身份，只按这个人看得到的、已确认的定义回答；问到没确认或需再看的定义，就拒答：令牌主人是建设者或管理员时，说明在等哪个定义、谁能确认；是查看者时，只说答案在等一个定义被确认。工具走 stdio，调用本机正在运行的服务，和页面用同一套接口：核验、计数、确认记录只有一份。这 6 个工具不能上传、写定义或确认，这些在页面里做；团队工作区里确认定义、批准提交的改动、记核对过的数，只认登录页面的人，带令牌的请求不论范围一律被拒绝。

早期界面（`legacy.html`，按运行建模）的 34 个工具还在，写在文末的[附录](#附录早期界面的工具)。什么时候会带出它们（`mcp_server.Toolset`）：

| 令牌 | 不设 `ONTOPOC_TOOLSET` | `ONTOPOC_TOOLSET=read` | `ONTOPOC_TOOLSET=all` |
|---|---|---|---|
| 没有令牌（本机会话） | 6 个只读 | 6 个只读 | 全部 40 个 |
| 只读令牌（“AI 工具接入”页默认） | 6 个只读 | 6 个只读 | 6 个只读 |
| 范围“全部”的令牌（个人在账号页建令牌时的默认） | **全部 40 个** | 6 个只读 | 全部 40 个 |

所以给外部智能体接的命令都写上 `ONTOPOC_TOOLSET=read`。

## 接上

先启动服务（`./scripts/ontopoc-start.sh`，或 `PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server`）。管理员在“AI 工具接入”页给一个人发令牌，再把工具服务配进客户端。Claude Code（在仓库根目录）：

```bash
claude mcp add ontopoc -- env ONTOPOC_TOKEN=<令牌> ONTOPOC_TOOLSET=read PYTHONPATH=$PWD/src python3 -m ontology_poc_generator.mcp_server
```

别的客户端写成 stdio 服务，命令同上；“AI 工具接入”页给出填好服务地址的 JSON，粘贴时在 `env` 里加上 `"ONTOPOC_TOOLSET": "read"`。服务不在 8767 端口时设 `ONTOPOC_URL`。

## 给外部智能体的只读工具

令牌是只读的、或设了 `ONTOPOC_TOOLSET=read` 时，工具服务只给这几个，按令牌主人（`ONTOPOC_TOKEN`）的权限算：

| 工具 | 做什么 | 调用模型 | 重试 |
|---|---|---|---|
| `describe_definitions` | 已确认的对象类型、属性、代码含义、关系、视图、派生属性和拒答规则，有另称的带着 `other_names`；`types` 只取几个类型和连着它们的定义（写英文名、名字或另称都行） | 否 | 可以 |
| `ontopoc_query` | 要一个数时先用它：直接写本体查询（像 SQL，见 [QUERY.md](QUERY.md)），代码算；写错时说明能写什么 | 否 | 可以，不记录 |
| `ask` | 写不出查询时才用：用一句话问，模型写成查询，代码算 | 是 | 每问一次都记进问答历史、算一次提问 |
| `list_unconfirmed` | 还不能用的定义，以及原因 | 否 | 可以 |
| `read_derived_property` | 读一个已确认的派生属性的值 | 否 | 可以 |
| `definition_standing` | 每条定义现在是不是已确认、谁确认的、什么时候、在哪个数据版本上，没确认的写明原因和可以确认的人；`id` 只看一条。同一份也在 `GET /api/workspace/agent/standing`（`?id=` 一条，`?format=csv` 已确认的定义表，最后一列是另称），技能包是快照，以这里为准 | 否 | 可以 |

`ask` 的回答带着 `query_text`，也就是这道题写成本体查询的样子。智能体可以先用 `ask` 学写法，再用 `ontopoc_query` 改条件、重复跑，后面这些都不再调用模型。

**问“哪些”和问某一个对象。** 问题问的是“哪些”（“哪些加急订单是高风险的”），或者 `ontopoc_query` 写的是 `SELECT LIST`，`answer` 是对象列表：`answer.total` 是令牌主人能看到的全部符合的个数，`answer.objects` 有 `columns`（代码列带确认过的 `meanings`）、这一页的 `rows`、`page`、`pages`、`page_size` 和 `order_by`。按主键排，一页最多 50 个；`ontopoc_query` 的 `page` 给第几页，`LIMIT n` 设每页个数，超过 50 会报错，不会悄悄截断。问某一个编号的对象（“措施 M-17 的审批状态”，或 `SELECT ONE`）时 `answer.lookup` 是那个主键，`answer.objects` 里是它能看的属性；令牌主人的行规则看不到的编号和不存在的编号回答一样，都是 `no_data`。条件里用了 `today` 时，`today` 字段写着用的是哪一天、哪个时区。这些行只回给调用的人或智能体，服务从不把它们发给问答的模型，也不存进问答历史（重开时按重开的人现在能看的重新算）。令牌拿到的和它的主人在页面上拿到的一样，主人是查看者时也一样：查看者本来就能在类型的“对象”页看到已确认类型的对象。两个工具仍是原来的标注：`ontopoc_query` 只读，`ask` 只添加问答历史。

`answer` 算的是令牌主人能看到的全部行时，`beside.views` 里还有这个类型上他看得到的每个已确认视图各自的数（`name`、`confirmed_by`、`answer`，最多 5 个，其余的名字在 `beside.more`）；`answer` 只算一个已确认视图时，第一条是全部行的数（`all_rows`）。`answer` 算哪些行和以前一样决定。`ontopoc_query` 的文字没有条件时同样带 `beside`。

这几个工具按给模型用的工具该有的样子来做（`tests/test_agent_tools.py` 守着）：

- **少，而且不重叠。** 连上时的说明、`ask` 的说明和拒答规则都写着：要数字先用 `ontopoc_query`，写不出来再用 `ask`。以前这三处都只提 `ask`，智能体会把能直接算的数也交给模型。
- **专门做一件事。** `ontopoc_query` 看起来像 SQL，但只能沿确认过的关系走、按提问人的行算，不是一个能读任何表的 `run_sql`（为什么见 [QUERY.md](QUERY.md)）。
- **省字。** 结果里不重复说同一件事：去掉了编译后的结构化查询（`text` 能编译回它），用到的定义只留 id、种类、名字、版本、确认人和派生属性的算式，状态只在不是已确认时给；属性的 `name` 只在和列名不同时给，`code` 只在是代码列时给。分组超过 50 组只给前 50 组，`groups_cut` 说一共几组、怎么用 `ORDER BY … LIMIT` 或 `WHERE` 收窄（`ask` 的回答是改它的 `query_text` 再用 `ontopoc_query` 跑）。`types` 写空列表会报错，要全部就不写。演示数据上，一个计数的结果从 424 个字降到 226 个（后来多了 `beside`，会长一些），全部定义从 4,620 降到 3,847，只取一个类型更少。
- **错误说怎么改。** 关系写错列出这个类型能走的关系，属性写错列出它的属性，缺参数写出 `"params": {"名字": …}` 的样子，类型不在定义里列出有的类型。
- **标明会不会改东西。** 每个工具都带 MCP 的 `annotations`（标题，和 `readOnlyHint`、`destructiveHint`、`idempotentHint`、`openWorldHint`）：上面的 6 个里除了 `ask` 都是只读的，`ask` 会把问题记进问答历史，标成只添加、不删改；早期界面里会覆盖已存内容或旧导出文件的工具标成 destructive；会让服务把数据发给模型的（`ask`，和早期界面的 `build_ontology`、`ask_question`、`draft_form`、`find_name_variants`）标 `openWorldHint`。这些只是给客户端的提示，拒绝什么仍由服务决定。
- **能放心重试。** 除了 `ask`，都是只读的，同样的调用在数据和定义没变时结果相同；`ask` 的说明里写着不要为了重试再问。

## 护栏照旧

这些是入口，不是新的 Agent：模型调用仍然只经过 `agent_harness.ask_model` 的六个 Agent，每个用户动作最多三次模型调用，答案由代码在数据上算。工具不改数据、不合并对象；确认和验收问题要调用方明确传入。只连本机。

## 附录：早期界面的工具

这些工具对应早期界面（`legacy.html`）的运行：上传文件建本体、看体检、记下客户的答复、逐项确认、导出。设了 `ONTOPOC_TOOLSET=all`，或用范围“全部”的令牌又没设 `read` 时就有（见上表）；Claude Code 插件（`/ontopoc:ontopoc-build`、`/ontopoc:ontopoc-review`）现在用的就是它们，插件默认设了 `all`。它们读的是一次运行里上传的数据，不经过团队应用的确认关口。

```bash
claude mcp add ontopoc-legacy -- env ONTOPOC_TOOLSET=all PYTHONPATH=<仓库路径>/src python3 -m ontology_poc_generator.mcp_server
```

本体库、⌘K 搜索和纪要、JSON 下载、新版本与“和上次比”的对比、建模记录没有对应的工具；稳定性只给到对象，不稳的关系在 open_items 里。

| 工具 | 对应页面上的 | 调用模型 |
|---|---|---|
| `health` | 服务状态、旧代码提示 | 否 |
| `list_runs` | 左下角的空间（运行记录） | 否 |
| `preview_upload` | "看看会发给模型什么" | 否 |
| `build_ontology` | 新建：上传并建本体，跑完才返回；`purpose` 是建模目的，给 `previous` 即作为那次运行的新版本，`mode: "org"` 按组织架构梳理一份文档 | 是 |
| `run_overview` | 运行概况：对象和关系数、体检通过几项、问答能答几道、稳定性，加“要确认的事”整张清单（`open_items`）、“客户已答复”（`answered_items`）和口径卡的格数（`card`） | 否 |
| `get_card` | 口径卡页：每张表一行是什么、日期列、数值列、对象全不全，和已答复的格 | 否 |
| `save_card` | 口径卡页「保存口径卡」；要确认的事「记下客户的回答」 | 否 |
| `list_objects` | 本体管理 · 对象卡片（判错的默认不给，列在 left_out；`include_wrong` 全给） | 否 |
| `object_fields` | 对象 · 属性 | 否 |
| `draft_form` | 对象 · 属性：起草中文名、描述、展示字段 | 是 |
| `save_form` | 对象 · 属性：保存 | 否 |
| `object_rows` | 对象 · 数据（`all=true` 相当于下载 CSV） | 否 |
| `list_relations` | 本体关系（同上）；基数带方向（`many_to_one` 等）和一句中文读法 | 否 |
| `suggest_relations` | 本体关系 · 代码建议的关系（虚线） | 否 |
| `find_instances` | 本体关系 · 实例图谱：找起点 | 否 |
| `instance_neighbourhood` | 本体关系 · 实例图谱：展开一个对象 | 否 |
| `data_layout` | 数据接入（含桥接提示） | 否 |
| `data_check` | 数据体检 | 否 |
| `list_rules` | 数据体检 · 规则 | 否 |
| `set_rules` | 数据体检 · 规则：采纳 / 不要 | 否 |
| `ask_question` | 智能问答 · 提问 / 出一组题 | 是 |
| `list_questions` | 智能问答 · 你问的、模型出的题、验收问题 | 否 |
| `confirm_derived` | 答案里「确认这个指标」：人同意后存下派生指标并重算等它的题 | 否 |
| `drop_filter` | 答案卡上“去掉这个条件重算”：去掉模型自己加的一个条件，由代码重算；条件可以照 `evidence.filters`（字段不带表名）写，也可以照 `query.where` 原样写 | 否 |
| `fix_question` | 存为验收问题（答案里有模型自己加的条件时，要写口径说明才放行） | 否 |
| `confirm_ontology` | 逐项确认 · 保存 | 否 |
| `compare_reference` | 数据体检 · 对照标准 | 否 |
| `list_proposed_views` | 本体 · 视图：别人提出、等另一个人确认的视图（带版本） | 否 |
| `confirm_proposed_view` | 本体 · 视图：确认别人提出的视图（带上看过的版本；提出人自己不能确认） | 否 |
| `find_name_variants` | 找出可能的对应 | 是 |
| `export_forms` | 右上角 ⤓ 表单：按对象表单导出 | 否 |
| `export_ttl` | 右上角 ⤓ TTL：按 W3C 标准导出 OWL 本体、数据与 SHACL 规则 | 否 |
| `export_mermaid` | 右上角 ⤓ 组织图：组织隶属与协作交接两张 Mermaid，可按年份段出图 | 否 |
| `export_pipeline_spec` | 右上角 ⤓ 编排需求单：交给搭管道的人，每张表要做的清洗、关联、按期取数和校验 | 否 |

四个导出工具把文件写进文件夹，只返回路径和字节数，不把内容塞进回复（TTL 的数据文件可以有几百万字）。默认写到 `~/Downloads/OntoPoc/<运行名>/<forms|ttl|mermaid|pipeline>/`，`out_dir` 可以指定别的绝对路径。

写之前先检查全部文件名：必须是单纯的文件名（不带文件夹，不是空的、`.`、`..`），有一个不合格就整次报错、一个文件也不写，所以文件不会落到 `out_dir` 外面。文件夹里会留一份清单 `.ontopoc-export.json`，按导出类型记着这次写了哪些文件；再导出到同一个文件夹时，上次清单里有、这次没有的文件会被删掉（比如人后来判错的对象的 CSV、撤掉规则后的旧 `shapes.ttl`），返回里的 `removed` 是删掉的文件名。清单以外的文件一律不碰。

`export_pipeline_spec` 生成编排需求单（`编排需求单.md` 和 `编排需求单.json`），交给搭数据管道的人：体检、要确认的事、口径卡、派生指标和采纳的规则里已经说了的“这份数据要怎么加工才能算对”，按表合成一份清单，每条写明来源（代码查出、客户答复、人确认）。它只描述要做什么，不执行加工，不调用模型，没有模型 key 也能导出。文档运行和没通过核验的运行没有需求单，服务返回 400 和原因，工具把它作为错误原样返回。

连上时工具服务会给客户端一份简短的使用说明：先调什么，哪几个工具调模型、要花钱，每种答案状态该怎么办，哪些判断只归人。`query_limit`、`ontology_gap` 要看题目里的 `reason_from_model`：为 true 是模型的判断，否则是代码查出来的原因（比如字段不存在、算法不支持）。`open_items` 里带 `requeried: true` 的条件项，是已经去掉条件重算过、验收题还是旧答案，要问的是换不换成新答案。

"下载纪要"没有单独的工具：纪要是页面把上面这些数据排版成的一页，开头就是 `run_overview` 里的 `open_items`。

### 口径卡和客户的答复

口径卡是每张上传的表一张：代码能算的先算好（一行按哪几列唯一、日期列的最早最晚和空值），只有人能答的留空，也就是一行是什么、日期列是什么时间、数值列能不能相加、对象在数据里全不全。`get_card` 读整张卡，每一格有稳定的 id，已答复的格带 `answer`（`value`、`says`、`by`、`basis`、`at`）。文档运行没有卡，返回空的 `tables`。

`save_card` 记的是人说的客户答复：`by`（答复人）和 `basis`（出处）都来自人，不替人填，不替客户答，也不按列名猜。`cells` 记卡上的格（`value` 为 null 是清空），`items` 记“要确认的事”里能答复的事（`model_filter`、`unjudged`、`card_blank` 不能用答复关掉）：每条写 `choice`（这件事自己的选项）或 `reply`（`confirm`、`wrong`、`not_applicable`、`exception`，各件事只收它的菜单里有的；代码含义和重复编号的确认走各自的接口，这里只收 `exception`），`reply` 为 `reopen` 是收回答复；给了 `items` 的请求在这份运行有更新版本时整次拒绝（400，有更新的版本）；也可以不给 `choice` 和 `reply`，只写 `text`；`mode` 只能是 `single`（默认），批量确认只有“一起通过”的接口能记；`not_applicable` 和 `exception` 还记着这件事当时依据的数据，再上传时数据变了（出现新的取值或编号，占比变了）它就重新出现，并写明变了什么；`exception` 必须写 `text`（原因）。校验不过整次不写，服务的 400 说明作为工具错误原样返回；写完服务会按新卡重新核对这次运行的验收题。返回 `{card, items, answered}`。

格的种类是 id 冒号前的那一段（`grain`、`date`、`range`、`amount`、`complete`）。每种格可选的值和各自的意思（例如 `running` 是“每次事件后的累计值”，`period_to_date` 是“期初到期末的累计值”）写在 `get_card`、`save_card` 的工具说明里，取自 `ontology_card.SAYS`，页面和纪要用的是同一套中文；客户说“这是累计数”时，照这些意思选 `value`，不按列名猜。

`unlinked` 的事答“数据没导全”（`incomplete`）时，服务会自动把另一端对象在卡上记成“只有一部分”（`partial`，格的答复里带着是哪件事记的）；这件事的答复改成别的，或不再是“数据没导全”，而那一格仍是这条答复记下的，服务就把它撤回。不用另发那一格。

`run_overview`（和 `build_ontology` 返回的概况）里，`answered_items` 是已记下客户答复的事，`card` 是 `{cells, blank}`，`blank` 是还没说清的格数。`answered_items` 在服务是旧版本、没有“要确认的事”这条路由时为 `null`；`card` 只有在旧版服务没有口径卡这条路由时才是 `null`，没有数据行的运行（文档、没通过核验）给 `{cells: 0, blank: 0}`。文档运行没有要和客户确认的事：不会去请求 `/open-items` 和 `/card`，`open_items`、`answered_items` 直接给 `[]`（旧版服务对文档的这两个请求会回 404 或 400，整个概况就取不出来了）。

问答照卡执行，全由代码完成：

- 数值列在卡上标成“每次事件后的累计值”，或标成“期初到期末的累计值”而问题没有固定在一期上，对它求和会被拒答：`status` 是 `query_limit`，`reason` 是代码给的原因（`reason_from_model` 不为 true），`refused_by_card` 是拒答的那一格的 id。照 `reason` 告诉人，这是口径卡上的规则，不要换问法绕过；平均不拦。
- 对象在卡上标成“只有一部分”时，答案照常给，`evidence.card.incomplete` 写明哪个对象、备注是什么，要转告人。
- 卡上至少有一格已答复时，`answered` 和 `no_data` 的答案带 `evidence.card`：`tables` 是用了哪张表、多少行、数据到哪天，`lines` 是答案按哪几条口径算的（谁答复、出处）。

# OntoPoc 的 MCP 工具

页面上的每个功能都有一个同名的 MCP 工具，任何支持 MCP 的客户端（Claude Code、Claude Desktop、Cursor、DSH 这类 agent）都能直接调用。工具走 stdio，调用的是本机正在运行的建模服务，和页面用同一套接口：核验、计数、确认记录只有一份。

## 接上

先启动建模服务（`PYTHONPATH=src python3 -m ontology_poc_generator.ontology_server`），再把工具服务配进客户端。Claude Code：

```bash
claude mcp add ontopoc -- env PYTHONPATH=<仓库路径>/src python3 -m ontology_poc_generator.mcp_server
```

别的客户端写成 stdio 服务，命令同上。服务不在 8767 端口时设 `ONTOPOC_URL`。

## 工具

| 工具 | 对应页面上的 | 调用模型 |
|---|---|---|
| `health` | 服务状态、旧代码提示 | 否 |
| `list_runs` | 左下角的空间（运行记录） | 否 |
| `preview_upload` | "看看会发给模型什么" | 否 |
| `build_ontology` | 新建：上传并建本体，跑完才返回；给 `previous` 即作为那次运行的新版本 | 是 |
| `run_overview` | 顶部的状态标签，加“要确认的事”整张清单（`open_items`）、“客户已答复”（`answered_items`）和口径卡的格数（`card`） | 否 |
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
| `find_name_variants` | 找出可能的对应 | 是 |
| `export_forms` | 右上角 ⤓ 表单：按对象表单导出 | 否 |
| `export_ttl` | 右上角 ⤓ TTL：按 W3C 标准导出 OWL 本体、数据与 SHACL 规则 | 否 |
| `export_mermaid` | 右上角 ⤓ 组织图：组织隶属与协作交接两张 Mermaid，可按年份段出图 | 否 |

三个导出工具把文件写进文件夹，只返回路径和字节数，不把内容塞进回复（TTL 的数据文件可以有几百万字）。默认写到 `~/Downloads/OntoPoc/<运行名>/<forms|ttl|mermaid>/`，`out_dir` 可以指定别的绝对路径。

写之前先检查全部文件名：必须是单纯的文件名（不带文件夹，不是空的、`.`、`..`），有一个不合格就整次报错、一个文件也不写，所以文件不会落到 `out_dir` 外面。文件夹里会留一份清单 `.ontopoc-export.json`，按导出类型记着这次写了哪些文件；再导出到同一个文件夹时，上次清单里有、这次没有的文件会被删掉（比如人后来判错的对象的 CSV、撤掉规则后的旧 `shapes.ttl`），返回里的 `removed` 是删掉的文件名。清单以外的文件一律不碰。

连上时工具服务会给客户端一份简短的使用说明：先调什么，哪几个工具调模型、要花钱，每种答案状态该怎么办，哪些判断只归人。`query_limit`、`ontology_gap` 要看题目里的 `reason_from_model`：为 true 是模型的判断，否则是代码查出来的原因（比如字段不存在、算法不支持）。`open_items` 里带 `requeried: true` 的条件项，是已经去掉条件重算过、验收题还是旧答案，要问的是换不换成新答案。

"下载纪要"没有单独的工具：纪要是页面把上面这些数据排版成的一页，开头就是 `run_overview` 里的 `open_items`。

## 口径卡和客户的答复

口径卡是每张上传的表一张：代码能算的先算好（一行按哪几列唯一、日期列的最早最晚和空值），只有人能答的留空，也就是一行是什么、日期列是什么时间、数值列能不能相加、对象在数据里全不全。`get_card` 读整张卡，每一格有稳定的 id，已答复的格带 `answer`（`value`、`says`、`by`、`basis`、`at`）。文档运行没有卡，返回空的 `tables`。

`save_card` 记的是人说的客户答复：`by`（答复人）和 `basis`（出处）都来自人，不替人填，不替客户答，也不按列名猜。`cells` 记卡上的格（`value` 为 null 是清空），`items` 记“要确认的事”里能答复的事（`model_filter`、`unjudged`、`card_blank` 不能用答复关掉）。校验不过整次不写，服务的 400 说明作为工具错误原样返回；写完服务会按新卡重新核对这次运行的验收题。返回 `{card, items, answered}`。

格的种类是 id 冒号前的那一段（`grain`、`date`、`range`、`amount`、`complete`）。每种格可选的值和各自的意思（例如 `running` 是“每次事件后的累计值”，`period_to_date` 是“期初到期末的累计值”）写在 `get_card`、`save_card` 的工具说明里，取自 `ontology_card.SAYS`，页面和纪要用的是同一套中文；客户说“这是累计数”时，照这些意思选 `value`，不按列名猜。

`unlinked` 的事答“数据没导全”（`incomplete`）时，服务会自动把另一端对象在卡上记成“只有一部分”（`partial`，格的答复里带着是哪件事记的）；这件事的答复改成别的，或不再是“数据没导全”，而那一格仍是这条答复记下的，服务就把它撤回。不用另发那一格。

`run_overview`（和 `build_ontology` 返回的概况）里，`answered_items` 是已记下客户答复的事，`card` 是 `{cells, blank}`，`blank` 是还没说清的格数。`answered_items` 在服务是旧版本、没有“要确认的事”这条路由时为 `null`；`card` 只有在旧版服务没有口径卡这条路由时才是 `null`，没有数据行的运行（文档、没通过核验）给 `{cells: 0, blank: 0}`。文档运行没有要和客户确认的事：不会去请求 `/open-items` 和 `/card`，`open_items`、`answered_items` 直接给 `[]`（旧版服务对文档的这两个请求会回 404 或 400，整个概况就取不出来了）。

问答照卡执行，全由代码完成：

- 数值列在卡上标成“每次事件后的累计值”，或标成“期初到期末的累计值”而问题没有固定在一期上，对它求和会被拒答：`status` 是 `query_limit`，`reason` 是代码给的原因（`reason_from_model` 不为 true），`refused_by_card` 是拒答的那一格的 id。照 `reason` 告诉人，这是口径卡上的规则，不要换问法绕过；平均不拦。
- 对象在卡上标成“只有一部分”时，答案照常给，`evidence.card.incomplete` 写明哪个对象、备注是什么，要转告人。
- 卡上至少有一格已答复时，`answered` 和 `no_data` 的答案带 `evidence.card`：`tables` 是用了哪张表、多少行、数据到哪天，`lines` 是答案按哪几条口径算的（谁答复、出处）。

## 护栏照旧

这些是入口，不是新的 Agent：模型调用仍然只经过 `agent_harness.ask_model` 的六个 Agent，每个用户动作最多三次模型调用，答案由代码在数据上算。工具不改数据、不合并对象；确认和验收问题要调用方明确传入。只连本机。

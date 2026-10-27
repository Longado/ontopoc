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
| `run_overview` | 顶部的状态标签，加“要确认的事”整张清单（`open_items`） | 否 |
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

## 护栏照旧

这些是入口，不是新的 Agent：模型调用仍然只经过 `agent_harness.ask_model` 的四个 Agent，每个用户动作最多三次模型调用，答案由代码在数据上算。工具不改数据、不合并对象；确认和验收问题要调用方明确传入。只连本机。

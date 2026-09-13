# 公开场景自动搭建本体 · 实施计划

> 背景、试验证据见 `docs/NHTSA_AUTO_ONTOLOGY_PLAN.md`；试验代码已在 A 轮后删除，试验记录在 `experiments/nhtsa_auto_ontology/recorded/`。本文是 A 轮的逐项实施计划，B、C、D 轮只定设计要点。步骤用 `- [ ]` 跟踪。

**目标：** 给一份公开数据快照和一个业务问题，系统自动搭建本体，用代码拿数据核验，按本体回答"召回范围内外有哪些同类投诉"，并给出可复核的候选清单。

**做法：** 模型只做两件判断（提出本体、读投诉原文），其余全部由 Python 完成：取数、核验、生成对象图、范围查询、证据核对、重试和停止。模型走现有 `OpenAICompatibleGateway`，在线运行只在独立脚本里发生，测试全部离线。

**技术栈：** Python 3.11 标准库（CI 用 3.11，本机 3.13 也要过）、`unittest`、现有 `model_gateway` 与 `identity`。

## 0. 设计决定

| 决定 | 选择 | 理由 |
|---|---|---|
| 本体输出格式 | 新结构 `public_ontology.v1`，**不塞进** `OntologySpec` | `OntologySpec` 要求 `DecisionPack` 哈希、只允许 `synthetic_demo`，`validation.py` 规定对象类型只能来自 `provided_input`；硬塞需要改合成链路的校验器，而公开链路没有任何消费方用到它。README 已约定公开召回数据不进这条链路，本轮沿用。**待用户拍板** |
| 编号 | ~~复用 `identity` 生成稳定编号~~ A 轮后删除 | 没有任何消费方，属于提前建设；真要并入 `OntologySpec` 时再加 |
| 本体能回答的问题 | 固定四个角色：事件、受影响对象、部件机制、信号 | 为"召回范围研判"这一类问题设计；不做任意问题的通用平台 |
| 查询只走直接关系 | 保留（试验时的做法） | 两跳路径由核验规则要求模型补直接关系；`ponytail:` 注释写明上限和升级路径（按关系链遍历） |
| 模型判断的地位 | 只产生"候选，待复核" | 试验证明文本判断随提示词摆动；B 轮标注集校准前不当结论 |
| 自动搭建的状态 | `auto_built_verified` 或 `blocked`，人工确认字段恒为 `pending` | 人工确认在 C 轮页面做；代码不自动把本体标成已确认 |
| 文本判断并发 | 串行（约 30 秒一批） | 在线脚本可以等；页面用录好的结果。`ponytail:` 注释写明需要时改线程池 |

## 1. 数据结构

**公开数据快照** `public_source_bundle.v1`（文件：`examples/nhtsa/chevrolet_bolt_2017_2023.json`）

```json
{
  "schema": "public_source_bundle.v1",
  "evidence_scope": "public_data",
  "decision": "一次汽车召回发布后，判断……（与试验相同的业务问题原文）",
  "sources": {
    "recalls":    {"requests": [{"url": "https://api.nhtsa.gov/recalls/recallsByVehicle?...", "retrieved_at": "2026-09-13T03:29:39Z"}], "records": []},
    "complaints": {"requests": [], "records": []}
  }
}
```

- 原始响应（A 轮后已并入快照文件并删除原件）取数时间 2026-09-13 03:29:39Z–03:31:11Z（按文件时间），每个请求的 `retrieved_at` 用对应文件时间。
- 召回按（活动号、车型、年款）去重，投诉按 `odiNumber` 去重；记录按这两个键排序后写入，保证记录下标稳定。
- 内容哈希 = 规范化 JSON 的 SHA-256，运行时计算，不存进文件。

**自动搭建的本体** `public_ontology.v1`

```json
{
  "schema": "public_ontology.v1",
  "evidence_scope": "public_data",
  "status": "auto_built_verified | blocked",
  "human_review": "pending",
  "decision": "...", "source_bundle_hash": "<sha256>",
  "model": "deepseek-flash", "prompt_version": "public_ontology_modeler.v2",
  "object_types": [{"type_id": "entity_type_<sha256>", "key": "vehicle_model_year", "label": "车型年款",
                    "role": "affected_object", "populated_from": [], "attributes": [], "rationale": "..."}],
  "relations": [{"relation_type_id": "relation_type_<sha256>", "key": "...", "from": "...", "to": "...",
                 "source": "complaints", "meaning": "..."}],
  "ignored_fields": [], "data_gaps": [],
  "verification": {"errors": [], "metrics": {"instances": {}, "shared_across_sources": {}, "links": {}}},
  "attempts": [{"errors": [{"code": "...", "message": "..."}]}]
}
```

**范围结果** `public_scope_result.v1`

```json
{
  "schema": "public_scope_result.v1",
  "ontology_hash": "<sha256>", "event": {"type": "recall_campaign", "identity": {"campaign_number": "21V650000"}},
  "covered": [{"make": "CHEVROLET", "model": "BOLT EV", "model_year": "2020"}],
  "mechanism": ["ELECTRICAL SYSTEM:PROPULSION SYSTEM:TRACTION BATTERY"],
  "candidates": [{
    "signal": {"odi_number": "11600123"}, "objects": [], "part_match": "same_part | same_category",
    "bucket": "inside_scope | covered_by_other_event | outside_all", "other_events": [],
    "source_refs": [{"source": "complaints", "index": 0}],
    "text_check": {"verdict": "yes | no | unknown", "reasoning": "...", "evidence": "...",
                   "model": "...", "prompt_version": "public_defect_match.v2"}
  }],
  "boundary": "候选，待质量工程师复核；不代表缺陷已确认、车辆已召回或已处置。"
}
```

**核验错误码**（每条错误是 `{"code", "message"}`，页面按 code 显示）：`invalid_response`、`unknown_source`、`unknown_field`、`empty_field`、`identity_keys_mismatch`、`transform_needs_single_field`、`mixed_list_identity`、`field_unaccounted`、`role_count`、`relation_unknown_type`、`relation_source_mismatch`、`relation_zero_links`、`role_relation_missing`、`sources_not_connected`。

## 2. A 轮任务

### 任务 1：公开数据快照

**文件：** 新建 `src/ontology_poc_generator/nhtsa_sources.py`、`tests/test_nhtsa_sources.py`、`examples/nhtsa/chevrolet_bolt_2017_2023.json`

- [x] 先写失败测试：缺 `requests` 或 `retrieved_at` 拒绝；`evidence_scope` 不是 `public_data` 拒绝；重复召回、重复投诉被去重；记录顺序稳定；同一文件两次加载哈希相同。
- [x] 实现 `load_source_bundle(path)` 和 `fetch_nhtsa_bundle(make, models, years, decision, opener=urlopen)`；取数函数只在脚本里被调用，测试用假 `opener`。
- [x] 用试验时的原始响应生成快照文件（13 个召回活动、679 条投诉），不重新取数，保证与试验结果可对照。
- [x] 运行 `PYTHONPATH=src python -m unittest tests.test_nhtsa_sources -v`，全过。

### 任务 2：本体核验与对象图

**文件：** 新建 `src/ontology_poc_generator/public_ontology.py`、`tests/test_public_ontology.py`、`tests/fixtures/nhtsa/mini_bundle.json`、`tests/fixtures/nhtsa/reference_proposal.json`

小样本 `mini_bundle.json` 从快照里按规则挑，不手编内容：召回 21V650000、20V701000、21V517000 的全部记录；投诉 11600123（2023 年款座椅下起火）、11429913（2019 年款召回配件未到）、11492459（2019 年款气囊未弹出）、11749605（转向问题），11429891（2020 年款、`fire=true` 的电气投诉）。`reference_proposal.json` 取 `experiments/nhtsa_auto_ontology/recorded/run_v2/ontology_attempts.json` 最后一次的 `spec`。2026-09-13 已用试验代码核对：该本体在这份小样本上通过全部核验，下面任务 4 的每条断言都成立。

- [x] 先写失败测试，每条核验规则一个用例，都在参照本体上做一处改动来触发：字段路径不存在；字段全空；同一类型两个来源身份键不同；有字段既没用上也没写忽略；某角色 0 个或 2 个；多字段身份用了 transform；身份字段来自两个不同列表；关系端点不在该来源；关系在数据里零连接；缺事件—受影响对象等四组关系之一；两个来源没有共享对象。
- [x] 再写对象图测试：冒号路径生成各级上级部件和上下级关系；逗号拆分；大小写和空白归一；参照本体在小样本上跨来源共享的车型年款、部件数量与手算一致。
- [x] 从试验代码 `experiments/nhtsa_auto_ontology/ontology.py` 移植 `validate_proposal`、`build_graph`、`graph_checks`，改成返回错误码；类型和关系编号用 `identity` 生成。
- [x] 运行该测试文件，全过。

### 任务 3：自动搭建循环

**文件：** 修改 `src/ontology_poc_generator/public_ontology.py`；新建 `tests/test_public_ontology_builder.py`、`tests/fixtures/nhtsa/recorded_modeler_attempts.json`（取自 `recorded/run_v2/ontology_attempts.json` 的两次 `spec`）

- [x] 先写失败测试（假网关按顺序返回录好的真实输出）：第一次缺关系 → 第二次请求里带着第一次的错误 → 第二次通过，结果 `status=auto_built_verified`、`attempts` 两条；错误数没有减少就停，`status=blocked`；模型返回非 JSON 或缺字段记为 `invalid_response`，不抛出；结果带 `model`、`prompt_version`、`source_bundle_hash`；`human_review` 恒为 `pending`。
- [x] 实现 `auto_build_ontology(bundle, gateway)`。提示词作为模块常量，版本号 `public_ontology_modeler.v2`，内容取试验第二版。字段目录（字段名 + 最多 3 个示例值）由代码生成，发给模型的只有问题文字和字段目录，不发全部记录。
- [x] 运行该测试文件，全过。

### 任务 4：范围查询

**文件：** 新建 `src/ontology_poc_generator/public_scope.py`、`tests/test_public_scope.py`

- [x] 先写失败测试（参照本体 + 小样本）：21V650000 覆盖 2020–2022 Bolt EV 和 2022 Bolt EUV；11429891 进 `inside_scope`；11600123 进 `outside_all`；11429913 进 `covered_by_other_event`，并列出 20V701000；11749605 不出现在候选里；21V517000 下 11492459 进 `outside_all`；本体被标 `blocked` 时拒绝查询。
- [x] 实现 `scope(ontology, bundle, event_identity)`，不调用模型。
- [x] 运行该测试文件，全过。

### 任务 5：投诉原文判断

**文件：** 修改 `src/ontology_poc_generator/public_scope.py`；新建 `tests/test_public_defect_match.py`

- [x] 先写失败测试（假网关）：按 20 条一批切分；返回里缺某条编号 → 该条 `unknown`；判 yes 但证据片段不在投诉原文里 → 降为 `unknown` 并写明原因；非法判断值 → `unknown`；召回描述取本体里事件类型声明的文本属性，投诉原文取信号类型声明的文本属性。
- [x] 实现 `check_candidates(scope_result, ontology, bundle, gateway)`，提示词版本 `public_defect_match.v2`，内容取试验第二版。
- [x] 运行该测试文件，全过。

### 任务 6：在线脚本

**文件：** 新建 `scripts/run_public_ontology.py`、`scripts/fetch_nhtsa_snapshot.py`、`tests/test_run_public_ontology.py`（实施时改为单独测试文件）

- [x] 先写失败测试：没有密钥环境变量 → 退出码 2，提示去本地配置；输出文件已存在 → 拒绝；默认模型 `deepseek-flash`；报告里不出现密钥。
- [x] 实现：读快照 → 自动搭建 → 对每个 `--campaign` 查范围并判断原文 → 写一份报告（本体 + 各召回的范围结果）；每一步打印进度，不打印密钥。
- [x] 在线跑一次：`--campaign 21V650000 --campaign 21V517000`，报告写到 `output/` 下的新文件。

### 任务 7：回归与文档

- [x] 运行全量回归：`PYTHONPATH=src python -m unittest discover -s tests -q`、前端 `test:unit`、`build`、`test:sites`、两个 artifact `--check`、`git diff --check`，记录确切数字。
- [x] README 加"公开场景自动搭建本体（本地）"一节：能做什么、怎么跑、边界（候选待复核、只到车型年款、四个角色）。
- [x] 在 `docs/NHTSA_AUTO_ONTOLOGY_PLAN.md` 第 4 节标 A 轮完成情况；删掉 `experiments/nhtsa_auto_ontology/` 里已被正式代码取代的部分，或在其开头写明已被取代。

### A 轮验收

- 离线测试覆盖上面每条核验规则、对象图、范围查询、原文判断和脚本约定，全部通过；原有 318 + 101 + 4 项不回退。
- 在线脚本对快照跑通两个召回：本体 `auto_built_verified`；电池召回的 `outside_all` 里有 43 条候选（与试验一致，数据相同则应一致），11600123 在其中。
- 新增代码无新依赖、无凭据、无本机绝对路径。

## 3. 后续轮次的设计要点

**B 轮 · 原文判断校准**
- 脚本生成一张标注表（CSV）：候选编号、召回描述、投诉原文、各提示词版本的判断，按优先级排序——试验中两版判断不一致的 101 条在前，其后是随机抽取的一致条目。标注人填 yes / no / unknown，标多少由标注人的时间决定。
- 同一脚本读回标注，报告每个提示词版本与人工一致的条数和分歧条目。不预设分数线，由用户决定用哪一版。
- 投诉自带的"起火"字段只作为参考对照，不当标准答案（它是投诉人自己填的）。

**C 轮 · 页面**
- 新增一个场景入口"公开召回范围研判"，三步：
  1. 看本体：对象、关系、忽略字段、数据缺口、核验数字；可以改名、删关系、改忽略字段，改完请本机服务重新核验，通过后"确认此版本"（写入确认时间，本地保存，可下载；不是审批系统）。
  2. 选召回：看覆盖的车型年款和三类候选，每条可以展开到原始记录。
  3. 复核候选：沿用召回工作台的复核部分，顺带修 WB-01（筛选后详情错行）。
- 核验和查询只在 Python 里算，页面不重写一遍；本机服务加两个接口（核验本体、查范围）。静态站只放一份录好的只读结果。

**D 轮 · 验证复用性**
- 同一套代码换一个品牌或车型的部件召回，从取数到范围结果不改代码。
- 可选：换一个领域（如 openFDA 药品召回）检验"自动搭建"是否只对 NHTSA 字段有效；四个角色不适用时如实记录，不为它扩框架。
- 然后找质量岗试用，记录用时、漏项、人工修正。

## 4. 这一轮不做

页面、标注集、企业字段、VIN 级判断、任意问题的通用本体平台、后端云部署、合入 main。

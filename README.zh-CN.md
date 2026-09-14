<picture>
  <source media="(prefers-color-scheme: dark)" srcset="landing-page/public/assets/ontopoc-logo.png">
  <img src="landing-page/public/assets/ontopoc-logo-light.png" alt="OntoPoc — Trace scope. Review evidence." width="420">
</picture>

# OntoPoc — Trace scope. Review evidence.

[English](README.md) · 中文

召回发布后，哪些同类投诉落在范围之外？OntoPoc 用两份公开数据（NHTSA 召回公告和车主投诉）替质量工程师回答这个问题：

1. 模型只看字段名和示例值，提出本体；代码拿全部记录核验（17 类错误），出错退回重做，最多三次。
2. 只出现在一个来源的名称交给模型提出对应；代码核验确实多连上记录才采纳，经对应连上的候选单独标出。
3. 每个召回由代码算出覆盖的车型年款和同部件投诉，分成本召回范围内、其他同部件召回已覆盖、所有召回之外三类，并标出召回前后；原文写明"修复后再召回"的连成系列。
4. 模型读投诉原文给初判；判"同一故障"必须引用原文，代码核对引用真在原文里。
5. 质量工程师在静态页面上逐条复核；复核结果就是校准第 4 步的标注。

验证数据：雪佛兰 Bolt EV / EUV 2017–2023（13 个召回、679 条投诉，2026-09-13 取数）与现代 Kona Electric / Kona EV 2019–2021（4 个召回、112 条投诉，2026-09-14 取数）。没有客户数据，范围没到车架号，没有部署。

数据来自 NHTSA 公开接口。OntoPoc 与 NHTSA、通用汽车、现代汽车无关联；它给出的候选和模型初判不是官方结论，也不构成缺陷认定。

方向说明：项目 2026-08-29 起步时是售前 POC 方案编译器，经供应链、合成质量演示、食品召回三次场景后，2026-09-13 定为召回范围研判。旧线已从分支删除，完整历史在标签 `archive-2026-09-13-nhtsa-review`。

> 开发前先读[开发护栏](docs/DEVELOPMENT_GUARDRAILS.md)；当前状态与下一步见 [接力文档](docs/HANDOFF_2026-09-13.md)、[功能清单](docs/FEATURES_2026-09-13.md)、[迭代 2 需求](docs/PRD_ITERATION_2.md)。

## 页面

```bash
cd landing-page && npm ci && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

打开 `http://127.0.0.1:5178`：默认场景"汽车召回范围研判（NHTSA）"读 `landing-page/public/data/` 下的静态数据（一份清单加每个数据集一个文件：雪佛兰 Bolt EV / EUV 2017–2023、现代 Kona Electric / Kona EV 2019–2021），不需要 Python 服务。左侧导航切换两个入口；召回范围研判分四个标签页：口径（核对系统怎么读这份数据，逐条判断名称对应；自动搭建的本体在"技术细节"里）→ 召回（按部件分组，接续召回连成系列）→ 复核（按召回后、起火/碰撞、日期排序；可用方向键和 1/2/3）→ 结果（与模型的一致情况、复核人、下载）。复核存在本机浏览器，可恢复、可下载；它是本机记录，不是审批。

`/landing` 是产品首页。第二个入口"事件 95876 核对清单"是 openFDA 食品召回的产品—批号核对，需要本机 Python 服务（见下）。

## 命令

```bash
PYTHONPATH=src python -m unittest discover -s tests -q          # 后端测试
npm --prefix landing-page run test:unit                           # 前端测试
npm --prefix landing-page run build && npm --prefix landing-page run test:sites
PYTHONPATH=src:. python scripts/build_public_review_pack.py --check   # 清单里每份数据是否与其运行报告一致

# 接一份新数据集，按顺序（第 3 步起需要本机 DeepSeek 凭据，见接力文档第 4 节；密钥不入库）
# 1. 从 NHTSA 取一个品牌、车型、年款区间的快照
PYTHONPATH=src:. python scripts/fetch_nhtsa_snapshot.py \
  --make chevrolet --model "bolt ev" --model "bolt euv" --years 2017-2023 --output examples/nhtsa/<快照>.json
# 2. 列出快照里的召回编号
PYTHONPATH=src:. python scripts/run_public_ontology.py --snapshot examples/nhtsa/<快照>.json
# 3. 用同一份快照在线运行：搭本体，再对选定的召回算范围、做初判
PYTHONPATH=src:. python scripts/run_public_ontology.py --snapshot examples/nhtsa/<快照>.json \
  --campaign 20V701000 --campaign 18V576000 --output output/public-ontology-<时间>.json
# 4. 留存运行记录，发布页面数据（同时更新 landing-page/public/data/index.json），再核对
cp output/public-ontology-<时间>.json examples/nhtsa/runs/<名称>.json
PYTHONPATH=src:. python scripts/build_public_review_pack.py --report examples/nhtsa/runs/<名称>.json --snapshot examples/nhtsa/<快照>.json
PYTHONPATH=src:. python scripts/build_public_review_pack.py --check
# 5. 页面的数据集下拉里就能选到它

# 复核之后：把下载文件汇入样本库，再比较规则、模型、先规则再看模型（只列条数）
PYTHONPATH=src:. python scripts/import_reviews.py --input <数据集>-review.json --reviewer <代号>   # 写进 examples/labels/（公开仓库：只存投诉编号和判断，不存投诉原文和车架号）
PYTHONPATH=src:. python scripts/compare_judgments.py --labels examples/labels/<数据集>.jsonl

# 用运行记录里的同一输入重跑模型初判，数一数有多少变了（需要凭据）
PYTHONPATH=src:. python scripts/check_stability.py --report examples/nhtsa/runs/<名称>.json --snapshot examples/nhtsa/<快照>.json --output output/stability-<时间>.json

# 事件 95876 本地核对服务与命令行
PYTHONPATH=src python -m ontology_poc_generator.recall_server
PYTHONPATH=src python -m ontology_poc_generator.recall_cli --product F-0369-2025/1 --lot X7547814
```

## 代码地图

| 文件 | 职责 |
|---|---|
| `src/ontology_poc_generator/nhtsa_sources.py` | 取数、去重、按来源统一日期、快照校验与哈希、召回编号引用 |
| `src/ontology_poc_generator/public_ontology.py` | 字段目录、本体核验（17 种错误码）、对象图、自动搭建循环、名称对应 |
| `src/ontology_poc_generator/public_scope.py` | 范围查询、召回前后、投诉原文判断与证据核对 |
| `src/ontology_poc_generator/public_review_pack.py` | 页面数据：分组、系列、候选、盲区统计 |
| `src/ontology_poc_generator/review_labels.py` | 复核下载文件汇入样本库；起火关键词规则；三种做法的条数对比 |
| `src/ontology_poc_generator/model_gateway.py`、`recognition.py` | OpenAI 兼容网关与模型调用契约 |
| `src/ontology_poc_generator/recall_*.py` | 事件 95876 核对（范围表、匹配、本地服务、DeepSeek 提取对照） |
| `landing-page/src/PublicRecallReview.jsx`、`publicReviewModel.js` | 复核页面与其纯函数 |
| `landing-page/src/RecallWorkspace.jsx`、`recallWorkspaceModel.js` | 事件 95876 工作台 |
| `landing-page/src/App.jsx` | 产品首页 |
| `examples/nhtsa/` | 快照与在线运行报告 |

## 边界

范围只到车型年款；模型初判仅供参考，还没有人工标注的回归样本；只在一份数据上验证过，四个角色（事件、受影响对象、部件机制、信号）是为召回与投诉的范围研判设计的，不是任意问题的本体平台；两个来源名称不同时靠核验过的名称对应补连，没被对应的仍会漏检，页面给出盲区统计；复核不代表缺陷已确认、车辆已召回或已处置。

许可证：MIT。

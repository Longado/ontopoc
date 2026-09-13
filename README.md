# OntoPoc — Trace scope. Review evidence.

**English summary.** OntoPoc answers one question for a quality engineer: after a recall is issued, which similar complaints fall outside its scope? It takes two public sources (NHTSA recall notices and owner complaints), lets a model propose an ontology from field names only, verifies that proposal in code against every record, aligns category names across sources with model-proposed and code-verified aliases, computes each recall's covered model years and same-part complaints in three buckets with before/after-recall timing, lets the model give a first verdict on each complaint text (quotes required and checked), and hands the final review to a human on a static web page whose reviews double as calibration labels. Verified on Chevrolet Bolt EV / EUV 2017–2023 (13 recalls, 679 complaints). No customer data, no VIN-level scope, no deployment yet. Documentation below is in Chinese.

召回发布后，哪些同类投诉落在范围之外？OntoPoc 把召回公告和车主投诉两份公开数据交给系统：模型自动搭建本体，代码逐项核验；跨来源名称对应由模型提出、代码核验；每个召回算出覆盖的车型年款和同部件投诉，分成范围内、其他召回已覆盖、所有召回之外，并标出召回前后；模型读投诉原文给初判（必须引用原文，代码核对引用真在原文里）；质量工程师在页面上逐条复核，复核结果就是校准模型的标注。

方向说明：项目 2026-08-29 起步时是售前 POC 方案编译器，经供应链、合成质量演示、食品召回三次场景后，2026-09-13 定为现在的召回范围研判；旧线已从分支删除，完整历史在标签 `archive-2026-09-13-nhtsa-review`。

> 开发前先读[开发护栏](docs/DEVELOPMENT_GUARDRAILS.md)；当前状态与下一步见 [接力文档](docs/HANDOFF_2026-09-13.md)、[功能清单](docs/FEATURES_2026-09-13.md)、[缺点与改进路线](docs/superpowers/plans/2026-09-13-improvement-roadmap.md)。

## 页面

```bash
cd landing-page && npm ci && npm run dev -- --host 127.0.0.1 --port 5178 --strictPort
```

打开 `http://127.0.0.1:5178`：默认场景"汽车召回范围研判（NHTSA）"读静态数据 `landing-page/public/data/nhtsa-bolt-review-pack.json`，不需要 Python 服务。四步：确认本体与名称对应 → 选召回（按部件分组，接续召回连成系列）→ 复核候选投诉（按召回后、起火/碰撞、日期排序）→ 看与模型的一致情况并下载。复核存在本机浏览器，可恢复、可下载；它是本机记录，不是审批。

`/landing` 是产品首页。第二个入口"事件 95876 核对清单"是 openFDA 食品召回的产品—批号核对，需要本机 Python 服务（见下）。

## 命令

```bash
PYTHONPATH=src python -m unittest discover -s tests -q          # 后端测试
npm --prefix landing-page run test:unit                           # 前端测试
npm --prefix landing-page run build && npm --prefix landing-page run test:sites
PYTHONPATH=src:. python scripts/build_public_review_pack.py --check   # 页面数据是否与运行报告一致

# 在线运行（需要本机 DeepSeek 凭据，见接力文档第 4 节；密钥不入库）
PYTHONPATH=src:. python scripts/run_public_ontology.py \
  --campaign 21V650000 --campaign 18V576000 --output output/public-ontology-<时间>.json
PYTHONPATH=src:. python scripts/build_public_review_pack.py --report output/public-ontology-<时间>.json

# 取另一个车型的快照
PYTHONPATH=src:. python scripts/fetch_nhtsa_snapshot.py \
  --make chevrolet --model "bolt ev" --years 2017-2023 --output examples/nhtsa/<名称>.json

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
| `src/ontology_poc_generator/model_gateway.py`、`recognition.py` | OpenAI 兼容网关与模型调用契约 |
| `src/ontology_poc_generator/recall_*.py` | 事件 95876 核对（范围表、匹配、本地服务、DeepSeek 提取对照） |
| `landing-page/src/PublicRecallReview.jsx`、`publicReviewModel.js` | 复核页面与其纯函数 |
| `landing-page/src/RecallWorkspace.jsx`、`recallWorkspaceModel.js` | 事件 95876 工作台 |
| `landing-page/src/App.jsx` | 产品首页 |
| `examples/nhtsa/` | 快照与在线运行报告 |

## 边界

范围只到车型年款；模型初判仅供参考，还没有人工标注的回归样本；只在一份数据上验证过，四个角色（事件、受影响对象、部件机制、信号）是为召回与投诉的范围研判设计的，不是任意问题的本体平台；两个来源名称不同时靠核验过的名称对应补连，没被对应的仍会漏检，页面给出盲区统计；复核不代表缺陷已确认、车辆已召回或已处置。

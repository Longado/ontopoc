# 示例场景：车辆召回范围研判

这是 OntoPoc 的一个行业示例，不是主产品。主产品是"上传一份业务文件，自动建本体并核验"，见 `PRODUCT.md`。这份文档收着这个示例的操作命令和代码位置，免得它们占掉 README。

页面入口在侧边栏"更多示例"下的"车辆召回范围"。它读 `landing-page/public/data/` 下的静态文件（一个索引加每个数据集一个文件：雪佛兰 Bolt EV / EUV 2017–2023、现代 Kona Electric / Kona EV 2019–2021），不需要 Python 服务。四个标签页：数据范围（看数据怎么读进来的、逐条判断名称对应；自动搭的本体收在技术细节里）→ 召回（按部件分组，再召回串成系列）→ 复核（按召回后、起火或碰撞、日期排序；方向键和 1/2/3 可用）→ 结果（与模型的一致率、复核人、下载）。复核记录存在本机浏览器里，是本地记录，不是批准。

`/landing` 是产品页。第二个入口"公开召回查询"对应 openFDA 事件 95876 的产品与批号匹配，需要下面的本机 Python 服务。

## 加一个数据集（按顺序，第 3 步起需要本机 DeepSeek 凭据，绝不提交凭据）

```bash
# 1. 从 NHTSA 取一个品牌、车型与年份的快照
PYTHONPATH=src:. python scripts/fetch_nhtsa_snapshot.py \
  --make chevrolet --model "bolt ev" --model "bolt euv" --years 2017-2023 --output examples/nhtsa/<snapshot>.json
# 2. 列出这个快照里的召回活动
PYTHONPATH=src:. python scripts/run_public_ontology.py --snapshot examples/nhtsa/<snapshot>.json
# 3. 在线跑同一个快照：建本体，再对选中的召回算范围和初判
PYTHONPATH=src:. python scripts/run_public_ontology.py --snapshot examples/nhtsa/<snapshot>.json \
  --campaign 20V701000 --campaign 18V576000 --output output/public-ontology-<time>.json
# 4. 留存这次运行，发布页面数据（同时更新 landing-page/public/data/index.json），再校验
cp output/public-ontology-<time>.json examples/nhtsa/runs/<name>.json
PYTHONPATH=src:. python scripts/build_public_review_pack.py --report examples/nhtsa/runs/<name>.json --snapshot examples/nhtsa/<snapshot>.json
PYTHONPATH=src:. python scripts/build_public_review_pack.py --check
# 5. 数据集会出现在页面的选择器里
```

## 复核之后

```bash
# 把下载的复核结果并入标注库，再比较规则、模型、先规则后模型（只比条数）
PYTHONPATH=src:. python scripts/import_reviews.py --input <dataset>-review.json --reviewer <code name>   # 写入 examples/labels/：公开仓库里只有投诉编号和判断，没有投诉正文和 VIN
PYTHONPATH=src:. python scripts/compare_judgments.py --labels examples/labels/<dataset>.jsonl

# 用同样的输入重跑模型的首次调用，数一数有多少条变了（需要凭据）
PYTHONPATH=src:. python scripts/check_stability.py --report examples/nhtsa/runs/<name>.json --snapshot examples/nhtsa/<snapshot>.json --output output/stability-<time>.json

# 每个数据集是否仍与它的运行记录一致
PYTHONPATH=src:. python scripts/build_public_review_pack.py --check

# 事件 95876 的本机服务与命令行
PYTHONPATH=src python -m ontology_poc_generator.recall_server
PYTHONPATH=src python -m ontology_poc_generator.recall_cli --product F-0369-2025/1 --lot X7547814
```

## 代码位置

| 文件 | 作用 |
|---|---|
| `src/ontology_poc_generator/nhtsa_sources.py` | 取数、去重、按来源统一日期、快照校验与哈希、召回引用 |
| `src/ontology_poc_generator/public_scope.py` | 范围查询、召回前后的时间判断、投诉正文核对与引用闸 |
| `src/ontology_poc_generator/public_review_pack.py` | 页面数据：分组、系列、候选、盲区计数 |
| `src/ontology_poc_generator/review_labels.py` | 复核下载并入标注库；起火关键词规则；规则 / 模型 / 先规则后模型的条数比较 |
| `src/ontology_poc_generator/recall_*.py` | 事件 95876 的查询（范围表、匹配、本机服务、DeepSeek 抽取核对） |
| `landing-page/src/PublicRecallReview.jsx`、`publicReviewModel.js` | 复核页与它的纯函数 |
| `landing-page/src/RecallWorkspace.jsx`、`recallWorkspaceModel.js` | 事件 95876 工作台 |
| `examples/nhtsa/` | 快照与留存的在线运行记录 |

## 这个示例的边界

范围只到车型年，公开召回数据没有 VIN。模型的判断是首次调用，还没有人工标注的回归集。只在一个数据集上验过；四个角色（事件、受影响对象、机理、信号）适合召回与投诉的范围问题，不适合任意问题。跨来源不同写法的名称只有经核验的对应才会打通，没打通的仍会漏，页面会报出有多少条投诉没有进入任何候选列表。复核不代表缺陷成立、车辆被召回或任何处置。

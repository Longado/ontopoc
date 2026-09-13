# Public Recall Scope Implementation Plan

> **For agentic workers:** Implementation is authorized. Execute inline using executing-plans; no delegation. Steps use checkboxes for progress.

**Goal:** 输入产品与批号，核对公开召回事件 95876 的范围、原文依据与信息缺口，并用 DeepSeek 实测公告提取。

**Architecture:** 保留 openFDA 原始 JSON；人工核对的产品分段明确绑定产品与批号，Python 计算四态。DeepSeek 使用现有 OpenAICompatibleGateway 提取候选，与核对表比较，不修改范围权威。现有工作台通过仅本地 API 展示结果。

**Tech Stack:** Python 标准库 / unittest，现有 React / Vite / Node test。无新增生产依赖。

## 全程边界

- 仅事件 95876 的公开历史召回范围；不是风险预测、正常检验、库存状态或食品安全建议。
- 原始公告使用 public_recall 范围，与 synthetic_demo、OntologySpec、ValidationReceipt 隔离。
- 公告名单用于核对，不将它同时作为预测输入与召回预测答案。
- 无数据库、登录、审批平台、外部写回、部署或推送。会话复核不持久化。
- 不修改主目录和其他工作树的既有内容。分支 codex/recall-scope-deepseek，基线 e92a748。
- DeepSeek 只接收公开公告；凭据仅从环境或用户指定本地配置读取，不写入产物。

## Round 1 — 可复核的确定性范围

Pain：公开 code_info 中多产品与批号混排，可能造成跨产品误匹配。
Decision：给定产品、批号以及可选 UPC/标签日期，是否在本公告范围内？
Outcome：CLI 返回 matched / insufficient / conflict / not_matched 与原文依据。
Non-goals：通用公告解析器、正常/安全判定、五系统事实补造。
Smallest path：examples/recalls/95876.openfda.json、95876.scope.json；src/ontology_poc_generator/recall_scope.py、recall_cli.py；tests/test_recall_scope.py。

- [x] 下载完整事件响应，保存 query URL、UTC 获取时间和原始响应。核对 5 个 recall_number。
- [x] 建立 12 个产品分段：F-0367-2025 的 8 个编号产品，另 4 条各一个产品。日期只在原文明确对应的分段中使用，不能将汇总数量分摊至批号。
- [x] 先写测试并验证失败：
  ```python
  result = match_recall(scope, {"product": "F-0369-2025/1", "lot": "X7547814"})
  self.assertEqual(result["status"], "matched")
  ```
- [x] 覆盖批号串品、缺信息、前缀不匹配、未知批号、UPC 冲突、标签日期边界以及源文本变动导致范围失效。
- [x] 实现 source-bound catalog loader 与 match_recall；先检查多标识冲突，再判断缺失，最后精确匹配。
- [x] CLI 命令：`PYTHONPATH=src python -m ontology_poc_generator.recall_cli --product F-0369-2025/1 --lot X7547814`。应输出 matched 和 F-0369-2025 的原文引用。
- [x] 执行 `PYTHONPATH=src python -m unittest tests.test_recall_scope -v`；通过后记录本轮结果。

## Round 2 — DeepSeek 公告提取实测

Pain：模型可能遗漏批号或把批号分配给错误产品。
Decision：模型提取的每个产品批号集合是否与核对表一致？
Outcome：逐公告保留模型版本、提取结果、差异与耗时，可区分离线检查和在线结果。
Non-goals：模型替代范围判断、四 Agent 编排、自动接受有差异输出。
Smallest path：recall_extraction.py、scripts/check_recall_deepseek.py、tests/test_recall_extraction.py；复用 model_gateway.py。

- [x] 先写接受精确提取、拒绝批号串品/遗漏/多出/重复产品/额外输出字段的测试，确认失败。
- [x] 每条原始公告一次 JSON 调用。提供 recall_number、product_description、code_info；候选格式为 `{"products":[{"product_key":"F-0369-2025/1","lots":["X7547814"]}]}`。
- [x] 对比候选和已核对 catalog，任何差异标记 rejected；不覆盖 catalog。
- [x] `PYTHONPATH=src python -m unittest tests.test_recall_extraction -v`。
- [x] 配置可用后执行 `PYTHONPATH=src python scripts/check_recall_deepseek.py --output output/recall-deepseek.json`，使用 DeepSeek 官方端点与模型。无密钥时如实报告 blocked，不能用 fake 通过替代在线测试。

## Round 3 — 现有工作台完成核对

Pain：CLI 难以由业务人员直接试用。
Decision：查看依据后，用户认可结果还是需要复核？
Outcome：现有页面输入产品/批号/可选 UPC 和日期，显示后端四态及原文，保留会话复核理由。
Non-goals：新路由、云后端、模型密钥入浏览器、第二份前端匹配逻辑。
Smallest path：recall_server.py、tests/test_recall_server.py；landing-page/src/RecallWorkspace.jsx、recallWorkspaceModel.js、recallWorkspaceModel.test.js、RecallWorkspace.css；StandaloneDemo.jsx 的场景切换；vite.config.mjs 的本地代理；README.md 使用说明。

- [x] 先测试本地 /api/recall/catalog 与 /api/recall/match、坏输入和未知路由，确认失败，再实现只绑定 127.0.0.1 的服务。
- [x] 先测试前端 API 错误处理及输入变化清除旧结果，再实现 UI。编辑输入时清除结果与人工复核；请求中禁用输入以避免旧响应覆盖新输入。
- [x] 启动 `PYTHONPATH=src python -m ontology_poc_generator.recall_server` 与 `npm run dev -- --host 127.0.0.1 --port 5178`。
- [x] 浏览器验证匹配、串品、缺批号、未知批号、来源展开、复核与输入修改后清除；检查窄屏和控制台。
- [x] 执行 Python 全测、现有前端 unit / build / sites、两份既有 artifact --check 和 git diff --check。

## 交付记录

每轮完成后补充：实际变更、验证命令与结果、DeepSeek 在线实测状态、下一轮唯一需要解决的阻塞。所有状态以实际执行为准。


### Round 1 结果

- 完成：保留 openFDA 原始响应；12 个产品分段、93 条产品—批号对应关系，加载时逐项校验原文分段、批号、UPC 与标签日期。
- 测试：先观察新模块缺失导致断言失败，再实现；`tests.test_recall_scope` 12 项通过。
- CLI 实际执行：`--product F-0369-2025/1 --lot X7547814 --label-date 2024-11-15` 返回 matched，原文与来源齐全。
- 边界：范围来自历史公告；不是库存/投料记录，也不能用此测试宣称召回预测成功。

### Round 2 结果

- 完成：DeepSeek 官方端点在线脚本；每条公告独立 JSON 提取，保留产品—批号分组、模型返回标识、耗时与逐项差异。复用既有 gateway。
- 测试：先失败再实现；`tests.test_recall_extraction` 4 项通过，含串品、遗漏、多出、重复、坏 JSON 和不向模型泄露核对答案。
- 首次在线尝试因缺少凭据退出码 2；凭据就绪后已完成实际调用，结果见下方在线续测记录。
- 凭据阻塞已解除；5 条公告均已用 DeepSeek 官方接口实测。

### Round 3 结果

- 完成：127.0.0.1 本地 Python API；原工作台新增场景切换与输入、四态、原文、会话复核。既有演示仍为默认场景。
- 测试：API 2 项和前端状态/API 3 项先失败后通过；本地请求验证、坏输入/超长请求/外部 Origin 拒绝。
- 浏览器：匹配、串品、缺批号、未匹配、证据展开、复核理由和修改输入后清除均已实际操作。桌面发现导航被横向 flex 拉伸，修正为内容区上方；导航高度由 608px 降至 72px。
- 390px 窄屏：documentWidth=390，无横向溢出；已查看桌面与窄屏截图。截图在 ignored `output/recall-qa/`，不包含凭据。
- 当前回归：Python 317 项、前端 unit 95 项；两份原 artifact --check 通过。Sites 检查依赖构建目录，首次先测后构建失败，按 build → test:sites 重跑 4 项通过。
- 构建保留既有 >500kB chunk 提示；不扩大范围做性能重构。
- DeepSeek 在线凭据阻塞已在续测中解除。未推送、合并或部署。


### Round 2 在线续测计划（2026-09-12）

- Outcome：用官方可用 DeepSeek 模型完成 5 条公开公告的在线提取对比。
- 边界：只发送公开公告；不改匹配规则或人工核对表；凭据只在当前进程使用。
- 实际发现：认证成功，`GET /models` 返回 deepseek-flash 与 deepseek-v4-pro。此前预设 deepseek-v4-flash 不在可用列表中。
- Smallest files：修正 scripts/check_recall_deepseek.py 的默认模型与 README 示例；tests/test_recall_extraction.py 加入默认模型回归；在线报告保存在 ignored output/。
- Proof：默认模型测试先因名称不符失败；修正后跑提取模块测试、5 次真实调用、后端回归和 diff 检查。

### Round 2 在线续测结果

- 模型：请求与返回均为 `deepseek-flash`；官方 `https://api.deepseek.com/chat/completions`，非 fake gateway。
- 五条公告全部 accepted；12 个产品分段、93 条产品—批号对应关系全部一致，无遗漏、多出或串品。
- 本次串行调用累计 22.626 秒；仅一次固定公开案例运行，不代表跨案例稳定性、召回预测或客户效果。
- 原始候选、模型与逐项耗时：`output/recall-deepseek-live-2026-09-12.json`。凭据未写入文件；进程已退出。
- 默认模型回归先失败后通过；后端全量 318 tests 通过，git diff --check 通过。前端本次未改，沿用上一轮 95 unit、4 Sites 与构建、浏览器检查证据。
- 当前三轮授权范围完成。后续若继续，优先另一个未用于当前规则设计的公告验证产品分组；不以同一案例重复通过替代泛化验证。

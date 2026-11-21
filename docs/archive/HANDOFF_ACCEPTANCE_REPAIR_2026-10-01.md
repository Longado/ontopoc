# OntoPoc 三处验收修复交接 · 2026-10-01

本轮只修复新上传选文件、验收题绑定快照保留、上传动作最多串联三次模型调用。上一轮 Agent Team 的 FAIL 报告保留为缺陷证据，不作为本轮通过依据。

## 范围与结果

- Pain：新文件选择被清空；删除其他验收题会隐式认可变化后的绑定；三次纠错建模后又自动调用问答。
- Decision：用户能从新上传开始检查草案，并决定是否明确重新认可变化后的验收题。
- Outcome：同步复制 FileList；列表编辑保留服务端原快照；明确 MCP `fix_question` 只重新认可指定题；三次建模后保留核验成功的草案，提示到“智能问答”单独提问。
- Non-goals：歧义选列、同类关系查询方向、新提示词、模型切换、预算变更、TTL 无损恢复、部署及其他候选功能。
- Smallest path：复用 UploadTab、savedAcceptance、现有 acceptance/fix_question 路径和 finish_build；没有生产依赖、路由或配置变更。

## 当前代码和验证

工作树 `.worktrees/acceptance-fixes-20261001`，分支 `codex/acceptance-workflow-fixes`，基线 `b228e40517b43f6b82578f8410d652200a615c29`，核心修复 `12f8b74597bd6626e641373fe9418bb2133a88f2`。失败测试独立提交后实现；未触及根工作树预先存在的 README、交接稿和 landing-page 改动。

本轮后端全量 651/651（无跳过）、前端 229/229、Sites 4/4 通过，生产构建和 diff 检查通过。Sites 检查依赖先生成构建产物，按此顺序执行后通过。日志在本机 `output/acceptance-repair/`，其中包括红/绿测试记录。

独立 HTTP/MCP 复验通过：删除 B 后 A 保持 broken 和原 CustomerId 快照，旧客户端缺失/空快照也不会隐式重新认可；下一次上传仍 broken。明确重新固定 A 后 A 使用 BillToId，B 的 broken 状态及原快照不变；下一次上传延续这一结果。三次建模的每条并行分支最多三次调用，没有追加自动问答；两次建模仍可追加一次目的问答。

## 新上传与后续入口

隔离页面 `http://127.0.0.1:5182/`，API `8771`，数据目录 `output/acceptance-repair/runs`，运行/磁盘指纹均为 `13ba7228cb0d`，模型就绪且服务未过期。临时运行配置位于忽略的 `output/`，没有改变生产配置。

实际 UI 新选公共 Chinook 工作簿显示文件卡并启用生成按钮；一次提交产生 `20261001T145458717Z-0d63536b.json`，10 对象、10 关系，主草案两次建模后核验成功。模型仍为 `deepseek/deepseek-v4.1-flash`、`company_ontology_modeler.v3`；使用原模型参数和预算。

新结果经独立原始 SQLite、工作簿和图逐项复核：8 名员工的 13 个自有属性与行来源正确，7 条员工→经理关系全部一致，无虚构经理；保存与现场重算的 data-fit 一致，7 项检查通过。语义报告保持 PARTIAL：实际数据通过，但模型生成的“Employee 1 自引用”缺口文字错误，原始 Employee 1 的 ReportsTo 为空，自引用 SQL 为 0 行。此错误没有影响图和 data-fit；本轮按用户限定不改提示词或增加功能，不能因此宣称完整语义质量已通过。

页面实际问答“员工有多少人？”返回 8。本轮完整操作、下载文件及最终独立审查状态以本机 `output/acceptance-repair/REPORT.md`、各 Agent 的 `verdict.json` 和审查记录为入口；GitHub 检查与合并以实际回执为准，不能从局部测试或本文提前推断。此次 Agent 代操作不等于非作者真人或客户验收。

原始证据入口：`output/acceptance-repair/{journey,semantic,compatibility}/`。后续继续时先读本轮 REPORT 和实际回执；不从旧报告推出本轮完成，也不开展额外功能。真人或客户验收仍需由真实试用者独立完成，不由 Agent 操作替代。

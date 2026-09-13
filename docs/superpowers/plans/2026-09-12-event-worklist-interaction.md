# Event Worklist Interaction Implementation Plan

> **For agentic workers:** Execute inline using executing-plans. Implementation is authorized. No delegation or additional approval checkpoint.

**Goal:** 解决 PM 审查的入口、数据对应与续办断点，让用户在事件 95876 下完成多条核对、修正、复核及本地恢复。

**Architecture:** 复用现有 Python 单条核对 API；前端清单只编排请求、展示后端结果、管理本地草稿。合成演示使用同一质量快照的标识与明确只读材料。无第二套前端匹配逻辑。

**Tech Stack:** 现有 React / Node test / Python unittest，浏览器 localStorage。无新增生产依赖。

## 范围与不做事项

- 本轮覆盖 UX-01 至 UX-07、UX-09；UX-08 的任意材料建模是后续独立能力，记录但不伪装已实现。
- 单事件 95876，最多 100 行；支持逐条新增或按制表符粘贴产品/批号/UPC/标签日期。不是通用 Excel 导入。
- 草稿在当前浏览器/源站本地保存，不同步、不外发；经办人字段是手工备注，不是已认证身份。
- 修改一行使该行结果、人工确认失效，其余行保留。公告版本变化使旧结果失效；损坏草稿不静默覆盖。
- 不改变召回算法、DeepSeek 提取提示词、真实系统权限、规则运行时或云部署。无新模型调用，因此不使用凭据。
- 保留前一轮全部工作；在现有隔离工作树实施，不移动仓库。

## 第一步：修复演示语义（UX-02/03/09）

Files：`landing-page/src/documentModelingDemoModel.js`、其 test、`DocumentModeler.jsx`、`RecallWorkspace.css`、必要的既有展示断言。

- [x] 测试先行：质量 preset.event.id 等于固定 artifact.quality_signal_id；所有范围对象 ID 在只读材料中出现；候选关系逐条对应快照事实，不能给 SHIP 与 WIP 编造绑定。
- [x] 将质量预设改为同一快照中的 event、abnormal unit、batch、WIP 核心图，材料注明完整范围对象和图的子集边界。
- [x] 固定文本改为 readOnly；生成后折叠材料并扩展结果宽度；保留展开按钮；控制按钮的 aria-label 包含 object_id。
- [x] 执行 `node --test landing-page/src/documentModelingDemoModel.test.js`，确认通过。

## 第二步：事件清单与本地恢复（UX-01/04/06/07）

Files：`landing-page/src/recallWorkspaceModel.js`、其 test、`RecallWorkspace.jsx`、`RecallWorkspace.css`、`StandaloneDemo.jsx`、必要的入口测试。

- [x] 先测试新增两行、编辑只清除一行结果/复核、批量粘贴空批号/错误列/超限、逐行失败不丢其他结果。
- [x] 建立 `{schema,event_id,catalogVersion,rows:[{id,query,result,review,error}]}` 草稿。row.id 只用于本地列表标识；匹配继续请求 `/api/recall/match`。
- [x] 先测试保存/恢复、错误 JSON、不支持版本、来源版本变化、quota/write 失败。验证先失败再实现。
- [x] 默认进入事件清单。提供三条明确标为演示查询的样例：列明批号、缺批号、串品；用户可以编辑或粘贴自己的待核对条目。
- [x] 列表显示产品/批号、系统结果、人工复核状态；独立详情编辑、单条重算和核对所有待核对项；操作中锁定编辑，避免旧响应覆盖新输入。
- [x] 人工“需补证”必须有补证事项，“认可”必须有依据说明；保留经办人备注。补充产品信息后重算，不把审核备注当事实。
- [x] 本地保存失败时显示错误，不能提示已保存；已有损坏草稿只显式清除后才能重新保存。

## 第三步：可见依据与交接（UX-05/07）

Files：同上及 `README.md`。

- [x] 展示输入产品、批号、UPC、日期是否填写及后端结论；原文用安全 React 文本节点高亮批号，不用 innerHTML。
- [x] 下载本地 JSON 摘要（事件、逐行输入/结果/复核及未执行边界）；它不是业务执行回执。
- [x] 更新 README 的入口、粘贴格式、本地存储范围和错误恢复方式。

## 验证与完成

- [x] `npm run test:unit`、`npm run build`、`npm run test:sites`。
- [x] `PYTHONPATH=src python -m unittest discover -s tests -q`；两份原 artifact --check；`git diff --check`。
- [x] 浏览器：三行不同结果 → 选中缺信息行 → 补批号重算 → 保存需补事项 → 切换/刷新恢复；原文高亮与摘要下载；桌面/390px 无溢出。
- [x] 检查只读合成材料、结果对应与折叠展开；查看截图，不仅看 DOM。
- [x] 更新问题记录与本文每一步的实际结果；不将后续任意材料建模写为已完成。

## 执行记录

2026-09-12：按上述顺序在原隔离工作树完成。先运行新增测试观察失败，再实现；最终 101 项前端、318 项后端与 4 项 Sites 测试通过。未增加依赖、未修改匹配算法、未提交或部署。

浏览器实际走通：添加三行 → 核对得匹配/缺信息/冲突 → 第 2 行补批号 → 单行重算 → 保存需补证事项 → 切换场景并刷新恢复 → 下载 JSON 摘要。另验证损坏草稿不覆盖、固定材料只读及折叠、原文批号高亮、桌面与 390px 布局。保存 quota 失败和来源变化由单元测试覆盖。复核表单未保存的编辑会显示提示；只有点击“保存本行复核”的内容进入草稿。请求 15 秒超时，逐行错误不阻止后续行，核对过程中禁用场景切换与输入。

截图和下载文件：`output/interaction-verification-2026-09-12/`。问题闭环详见 `docs/PM_INTERACTION_ISSUES.md`。

## 下一轮独立步骤：UX-08（尚未实施）

目标：用户从材料得到可人工纠正的候选产品/批号范围；不能直接把模型文本当成核对规则。

1. 确定支持的材料格式和一个公开事件，保留原文、来源与产品分段；不扩展到任意企业文档或真实库存接入。
2. 接入既有 DeepSeek 提取模块，显示读取、提取、校验及失败状态；仅使用本机环境凭据，记录实际模型名与本次输入来源。
3. 展示候选与原文对应，允许逐产品修正批号、条码和日期；缺引用或结构不合格时不能应用。
4. 人工确认后生成新公告范围版本，再交给确定性匹配器；旧草稿结果失效，保留输入并要求重算。
5. 用公开样本完成“提取失败恢复、候选纠错、确认应用、旧清单重算”浏览器验收，并用 DeepSeek 实测验证。

这部分需要新增材料与版本应用流程，超出本轮固定公告清单的修改范围，不计入本轮完成项。

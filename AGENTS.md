# OntoPoc 开发与 PR 收尾

先读 `docs/DEVELOPMENT_GUARDRAILS.md`。保持最小改动、模型提议/代码核验/人决定；每次操作最多串联 3 次模型调用。测试数据使用隔离目录，真实业务数据留在本机。密钥只能从本机环境加载，不提交或上传。

## 开发验证

行为变更先写失败测试、运行确认失败并单独提交，再实现。修改已有测试前先 `touch ~/.claude/.allow-test-edit`，测试规格变更单独提交。功能/修复按相关测试、临时 `--data-dir` 真实模型试跑、离屏页面截图验证后开 PR；纯文档或 GitHub 设置变更不重复调用模型。新分支从更新的 `origin/main` 创建，不切换或删除别人占用的 worktree。

## 自动审查与合并（2026-09-27 用户授权）

用户已授权我们开发的 PR 在独立审查与检查通过后自动合并，包含 #48，无需逐次询问。适用范围必须同时满足：

- 仓库及 PR 的 head 仓库都是 `Longado/ontopoc`，base 是 `main`；
- PR 作者是 `Longado`，head 分支以 `codex/` 开头，且由本工作流开发；
- PR 非草稿。外部贡献、其他分支或无法确认归属的 PR 不自动合并。

执行顺序：

1. 推送后读取 PR 的最新 head SHA 和 base SHA。派独立 reviewer agent 审查该版本相对 base 的完整改动；交代需求、改动范围与测试证据，不让实现者代替独立审查。
2. 先修复阻断问题并完成相关验证。新增提交后重新审查；有未解决的阻断、失败/取消的检查、冲突或缺少必要验证时保持 PR 打开，明确报告原因，不能为了合并跳过要求。
3. 审查通过后再次核对 head SHA 没变，将审查摘要作为 PR review comment 发布，写明审查 SHA、范围、验证及结论；保留 comment URL。
4. 在**已审查的完整 SHA** 上通过 `gh api repos/Longado/ontopoc/statuses/<SHA>` 发布 `ontopoc/agent-review=success`，`target_url` 指向该审查评论。测试绿不等于审查通过；不能给未经审查的新 SHA 复用成功状态。
5. 核对适用范围及 `unittest`、`page`、`ontopoc/agent-review` 状态；执行 `gh pr merge <N> --repo Longado/ontopoc --auto --merge --match-head-commit <SHA>`，由 GitHub 等待必需检查并合并。不得使用 `--admin`、强制推送或删除保护规则绕过门槛。若 head/base 变化，更新分支后回到审查和验证步骤。
6. 查询 GitHub 确认 `MERGED` 和 merge commit 后再报告已合并；仅启用 auto-merge 不代表已经合并。保留服务使用的 worktree/分支，新工作从最新 `origin/main` 开始。

GitHub `main` 要求分支更新到最新、全部必需检查通过且审查讨论已解决；管理员也受保护。审查由开发会话中的 agent 执行，GitHub 只负责检查和自动合并；这里没有安装常驻 AI 审查服务。其他 PR 仍由维护者决定，并满足同样的主分支检查门槛。

// The 设置 · 工作区 page's rows, as plain functions of what the service sends, so they can be tested without a browser.
// A row is {key, title, state: "ok" | "warn" | "unknown", text, link: {label, href} | null}.

/** The two files an operator keeps a copy of (docs/DEPLOY.md, 数据和备份). */
export const BACKUP_FILES = [
  { file: "workspace.sqlite", what: "全部数据集、定义、确认记录、回答、日志，以及账号的密码哈希和登录会话" },
  { file: "sources.key", what: "封存数据源密码的钥匙。没有它，数据源的密码读不出来，要重新填" },
];

/** `modelReady` (true/false, null when unknown), `twoPerson` ({enabled, active, builders} or null), `health` ({running, stale} or null). */
export function workspaceRows({ modelReady = null, twoPerson = null, health = null }) {
  const model = modelReady === null
    ? { state: "unknown", text: "读不到模型状态。" }
    : modelReady
      ? { state: "ok", text: "已配置。问数和 AI 建议可以用。" }
      : { state: "warn", text: "没有配置模型：问数回答不了问题，AI 建议也用不了。启动服务时按部署文档配置模型的密钥。" };
  let two;
  if (!twoPerson) two = { state: "unknown", text: "读不到两人确认的设置。" };
  else if (!twoPerson.enabled) two = { state: "warn", text: "关着：一个人建的东西，自己确认就算数。" };
  else if (!twoPerson.active) two = { state: "warn", text: `开着，但现在能确认的只有 ${twoPerson.builders} 人，所以暂时自己确认自己建的也算数。再邀请一位建设者就按两人确认来。` };
  else two = { state: "ok", text: `开着：一个人建的东西，要另一个建设者确认才算数（现在能确认的有 ${twoPerson.builders} 人）。` };
  let build;
  if (!health || !health.running) build = { state: "unknown", text: "读不到版本信息。" };
  else if (health.stale) build = { state: "warn", text: `当前运行的版本 ${health.running}，但程序文件在启动后改过了，需要重启服务才会生效。` };
  else build = { state: "ok", text: `当前运行的版本 ${health.running}，与磁盘上的程序文件一致。` };
  return [
    { key: "model", title: "问答模型", ...model, link: null },
    { key: "two", title: "两人确认", ...two, link: { label: "去用户页调整", href: "#/users" } },
    { key: "build", title: "服务版本", ...build, link: null },
  ];
}

import { t } from "./i18n/index.js";

// The 设置 · 工作区 page's rows, as plain functions of what the service sends, so they can be tested without a browser.
// A row is {key, title, state: "ok" | "warn" | "unknown", text, link: {label, href} | null}.

/** The two files an operator keeps a copy of (docs/DEPLOY.md, 数据和备份). */
export const BACKUP_FILES = [
  { file: "workspace.sqlite", get what() { return t("settings.file.workspace"); } },
  { file: "sources.key", get what() { return t("settings.file.key"); } },
];

/** `modelReady` (true/false, null when unknown), `twoPerson` ({enabled, active, builders} or null), `health` ({running, stale} or null). */
export function workspaceRows({ modelReady = null, twoPerson = null, health = null }) {
  const model = modelReady === null
    ? { state: "unknown", text: t("settings.model.unknown") }
    : modelReady
      ? { state: "ok", text: t("settings.model.ok") }
      : { state: "warn", text: t("settings.model.warn") };
  let two;
  if (!twoPerson) two = { state: "unknown", text: t("settings.two.unknown") };
  else if (!twoPerson.enabled) two = { state: "warn", text: t("settings.two.off") };
  else if (!twoPerson.active) two = { state: "warn", text: t("settings.two.inactive", { count: twoPerson.builders }) };
  else two = { state: "ok", text: t("settings.two.active", { count: twoPerson.builders }) };
  let build;
  if (!health || !health.running) build = { state: "unknown", text: t("settings.build.unknown") };
  else if (health.stale) build = { state: "warn", text: t("settings.build.stale", { version: health.running }) };
  else build = { state: "ok", text: t("settings.build.ok", { version: health.running }) };
  return [
    { key: "model", title: t("settings.model.title"), ...model, link: null },
    { key: "two", title: t("settings.two.title"), ...two, link: { label: t("settings.two.link"), href: "#/users" } },
    { key: "build", title: t("settings.build.title"), ...build, link: null },
  ];
}

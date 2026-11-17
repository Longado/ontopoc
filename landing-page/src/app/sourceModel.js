import { KEY_SEPARATORS } from "./serverWords.js";
import { formatNumber, t } from "./i18n/index.js";

// What the sources and schedules pages say and check, as plain data so it can be tested without a browser. The service decides; these choose the words.
export const KINDS = [
  { key: "postgresql", label: "PostgreSQL", port: 5432 },
  { key: "mysql", label: "MySQL", port: 3306 },
];
export const kindPort = (kind) => KINDS.find((k) => k.key === kind)?.port ?? 5432;

/** Encryption choices in the current language (getters: read at use time). */
export const TLS_MODES = [
  { key: "required", get label() { return t("sources.tls.required"); } },
  { key: "none", get label() { return t("sources.tls.none"); } },
];
export const tlsWarning = () => t("sources.tls.warning");
const LOCAL_HOSTS = ["localhost", "127.0.0.1", "::1", "[::1]"];
/** Encryption to start from: off for a database on this machine, on for any other. */
export const tlsDefault = (host) => (LOCAL_HOSTS.includes(String(host ?? "").trim().toLowerCase()) ? "none" : "required");

/** Weekday names, Monday first, in the current language. */
export const weekdayNames = () => ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].map((d) => t(`sources.weekday.${d}`));
export const CADENCES = ["hourly", "daily", "weekly", "upstream"].map((key) => ({ key, get label() { return t(`sources.cadence.${key}`); } }));

const word = (area, map, key) => (key in map ? t(`${area}.${key}`) : key);
const STATUS = { untested: 1, ok: 1, failed: 1 };
export const statusText = (source) => word("sources.status", STATUS, source.status);

const RUN_STATUS = { running: 1, success: 1, failed: 1, skipped: 1 };
const REASON = { manual: 1, schedule: 1, upstream: 1 };
export const runStatusText = (run) => word("sources.run", RUN_STATUS, run.status);
export const reasonText = (run) => word("sources.reason", REASON, run.reason);

/** The row count of a table the database estimated: said to be an estimate, since it comes from the database's statistics and may be old. */
export const estimateText = (rows) => (rows == null ? t("sources.estimate.none") : t("sources.estimate", { n: formatNumber(rows) }));

/** One run in a line: what it read or wrote, or why it did not. */
export function runSummary(run) {
  if (run.status === "failed" || run.status === "skipped") return run.error ?? "";
  if (run.status === "running") return "";
  if (run.hidden) return t("sources.run.hidden");
  const parts = [];
  if (run.rows != null) parts.push(t("data.n.rows", { count: run.rows }));
  if (run.version != null) parts.push(t("sources.run.version", { n: run.version }));
  if (run.changed === false) parts.push(t("sources.run.same"));
  const flagged = run.detail?.flagged_count ?? run.detail?.flagged?.length ?? 0;
  if (flagged) parts.push(t("sources.run.flagged", { count: flagged }));
  if (run.detail?.left_out?.length) parts.push(t("sources.run.leftOut", { cols: run.detail.left_out.join(t("data.listSep")) }));
  return parts.join(t("data.sep"));
}

/** "source:订单库/orders" -> {source, table}; anything else (an upload, a pipeline run) -> null. */
export function sourceOrigin(origin) {
  const found = /^source:([^/]+)\/(.+)$/.exec(origin ?? "");
  return found ? { source: found[1], table: found[2] } : null;
}

/** The key columns a person typed ("订单号, 行号" or "订单号、行号"), as a list. */
export const keyColumnsFrom = (text) => String(text ?? "").split(KEY_SEPARATORS).filter(Boolean);

const MOVES = ["host", "port", "database", "username"];

/** What is missing from a source form before it is sent; "" when nothing. A blank password is fine when editing (the one saved is kept) as long as the host, port,
 * database and account are still the saved ones: a saved password is not sent to a new place without being typed again. `saved` is the source being edited. */
export function sourceProblem(form, editing, saved) {
  if (!editing && !form.name.trim()) return t("sources.problem.name");
  if (!form.host.trim()) return t("sources.problem.host");
  if (/[\s/@?#]/.test(form.host.trim()) || form.host.includes("://")) return t("sources.problem.hostShape");
  if (form.host.includes(":") && !/^\[?[0-9a-fA-F:.]+\]?$/.test(form.host.trim())) return t("sources.problem.hostPort");
  const port = Number(form.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) return t("sources.problem.port");
  if (!form.database.trim()) return t("sources.problem.database");
  if (!form.username.trim()) return t("sources.problem.username");
  if (!editing && !form.password) return t("sources.problem.password");
  const moved = editing && saved ? MOVES.filter((k) => String(form[k]).trim() !== String(saved[k])).map((k) => t(`sources.moved.${k}`)) : [];
  if (moved.length && !form.password) return t("sources.problem.moved", { what: moved.join(t("data.listSep")) });
  const ca = String(form.ca ?? "").trim();
  if (ca && !ca.includes("-----BEGIN CERTIFICATE-----")) return t("sources.problem.caPem");
  if (ca && (form.tls ?? tlsDefault(form.host)) === "none") return t("sources.problem.caUnused");
  return "";
}

/** The request for saving a source: the port as a number, no password when it is blank (the saved one stays), and ca_pem only when a CA was pasted
 * ("" when it is taken away; nothing with encryption off). */
export function sourceBody(form, tls) {
  const { ca, dropCa, password, ...rest } = form;
  const pasted = String(ca ?? "").trim();
  return { ...rest, tls, port: Number(form.port), ...(password ? { password } : {}),
    ...(tls === "required" && pasted ? { ca_pem: pasted } : tls === "required" && dropCa ? { ca_pem: "" } : {}) };
}

/** What is missing from a schedule form before it is sent; "" when nothing. */
export function scheduleProblem(form, sources, pipelines) {
  if (!form.name.trim()) return t("sources.problem.name");
  if (!form.target) return form.kind === "source" ? t("sources.problem.pickSource") : t("sources.problem.pickPipeline");
  if (form.kind === "source" && !sources.find((s) => s.name === form.target)?.tables.length) return t("sources.problem.noTables");
  if (form.kind === "pipeline" && !pipelines.some((p) => p.name === form.target)) return t("sources.problem.noPipeline");
  if (form.cadence === "hourly" && !(Number.isInteger(Number(form.minute)) && form.minute !== "" && form.minute >= 0 && form.minute <= 59)) return t("sources.problem.minute");
  if ((form.cadence === "daily" || form.cadence === "weekly") && !/^([01]\d|2[0-3]):[0-5]\d$/.test(form.time)) return t("sources.problem.time");
  if (!form.tz.trim()) return t("sources.problem.tz");
  return "";
}

/** The request body of a schedule form. */
export function scheduleBody(form) {
  const body = { name: form.name.trim(), kind: form.kind, target: form.target, cadence: form.cadence, tz: form.tz.trim() };
  if (form.cadence === "hourly") body.minute = Number(form.minute);
  if (form.cadence === "daily" || form.cadence === "weekly") body.time = form.time;
  if (form.cadence === "weekly") body.weekday = Number(form.weekday);
  if (form.kind === "source" && form.scope?.length) body.scope = form.scope;
  return body;
}

/** The pipelines a schedule may name: the ones that can be run on a clock (confirmed, or waiting on new data only). */
export const runnablePipeline = (p) => p.state === "confirmed" || (p.state === "needs_look" && p.cause === "data" && p.via === "self");

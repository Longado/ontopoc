// What the sources and schedules pages say and check, as plain data so it can be tested without a browser. The service decides; these choose the words.
export const KINDS = [
  { key: "postgresql", label: "PostgreSQL", port: 5432 },
  { key: "mysql", label: "MySQL", port: 3306 },
];
export const kindPort = (kind) => KINDS.find((k) => k.key === kind)?.port ?? 5432;

export const WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
export const CADENCES = [
  { key: "hourly", label: "每小时" },
  { key: "daily", label: "每天" },
  { key: "weekly", label: "每周" },
  { key: "upstream", label: "上游更新时" },
];

const STATUS = { untested: "未测试", ok: "正常", failed: "失败" };
export const statusText = (source) => STATUS[source.status] ?? source.status;

const RUN_STATUS = { running: "进行中", success: "成功", failed: "失败", skipped: "跳过" };
const REASON = { manual: "手动", schedule: "定时", upstream: "上游更新" };
export const runStatusText = (run) => RUN_STATUS[run.status] ?? run.status;
export const reasonText = (run) => REASON[run.reason] ?? run.reason;

/** One run in a line: what it read or wrote, or why it did not. */
export function runSummary(run) {
  if (run.status === "failed" || run.status === "skipped") return run.error ?? "";
  if (run.status === "running") return "";
  const parts = [];
  if (run.rows != null) parts.push(`${run.rows} 行`);
  if (run.version != null) parts.push(`第 ${run.version} 版`);
  if (run.changed === false) parts.push("和上一版一样，没有写新版本");
  const flagged = run.detail?.flagged?.length ?? 0;
  if (flagged) parts.push(`${flagged} 项已确认的内容进了“需要再看”`);
  if (run.detail?.left_out?.length) parts.push(`没读的二进制列：${run.detail.left_out.join("、")}`);
  return parts.join("，");
}

/** "source:订单库/orders" -> {source, table}; anything else (an upload, a pipeline run) -> null. */
export function sourceOrigin(origin) {
  const found = /^source:([^/]+)\/(.+)$/.exec(origin ?? "");
  return found ? { source: found[1], table: found[2] } : null;
}

/** The key columns a person typed ("订单号, 行号" or "订单号、行号"), as a list. */
export const keyColumnsFrom = (text) => String(text ?? "").split(/[,，、\s]+/).filter(Boolean);

/** What is missing from a source form before it is sent; "" when nothing. A blank password is fine when editing (the one saved is kept). */
export function sourceProblem(form, editing) {
  if (!editing && !form.name.trim()) return "要填名字";
  if (!form.host.trim()) return "要填主机";
  if (/[\s/@?#]/.test(form.host.trim()) || form.host.includes("://")) return "主机只写地址，不要带协议、路径或账号";
  const port = Number(form.port);
  if (!Number.isInteger(port) || port < 1 || port > 65535) return "端口要写成 1 到 65535 的整数";
  if (!form.database.trim()) return "要填数据库名";
  if (!form.username.trim()) return "要填账号";
  if (!editing && !form.password) return "要填密码";
  return "";
}

/** What is missing from a schedule form before it is sent; "" when nothing. */
export function scheduleProblem(form, sources, pipelines) {
  if (!form.name.trim()) return "要填名字";
  if (!form.target) return form.kind === "source" ? "要选一个数据源" : "要选一条管道";
  if (form.kind === "source" && !sources.find((s) => s.name === form.target)?.tables.length) return "这个数据源还没有读成数据集的表：先到它的页面读一张表";
  if (form.kind === "pipeline" && !pipelines.some((p) => p.name === form.target)) return "没有这条管道";
  if (form.cadence === "hourly" && !(Number.isInteger(Number(form.minute)) && form.minute !== "" && form.minute >= 0 && form.minute <= 59)) return "每小时的第几分写 0 到 59";
  if ((form.cadence === "daily" || form.cadence === "weekly") && !/^([01]\d|2[0-3]):[0-5]\d$/.test(form.time)) return "时间写成 08:30 这样";
  if (!form.tz.trim()) return "要填时区";
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

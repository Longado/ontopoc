export const ACCEPT = ".csv,.xlsx,.md,.txt,.docx,.pdf";
export const DEMO_URL = "/data/demo-company-result.json";
export const DEMO_DOC_URL = "/data/demo-document-result.json";
export const RESULT_KEY = "ontopoc.studio.last-result";
export const CHECK_LABELS = {
  fields_accounted: "每个字段都有去处（用上或写明不用）",
  identity_consistent: "同一个对象在不同行里的信息不打架",
  identity_spelling: "同一个编号只有一种写法（不混用大小写、空格）",
  relations_link: "每条关系都在数据里真的连上了",
  references_resolve: "引用的对象都能在它所属的表里找到",
  sources_connected: "所有表通过共同的对象连成一片",
  sources_used: "每张传上来的表都被本体用上了",
  quotes_verified: "模型提出的每一项都能在原文里找到引用",
  no_isolated_concepts: "抽出来的概念，每个都至少连着一条抽出来的关系",
  every_period_dated: "每个时期的年份都在原文里写着",
  every_role_placed: "每个岗位都说清了属于哪里，或者和谁交接",
};

export const COVERAGE_NOTE = "所有结论只覆盖这一次上传的文件；别的系统里有没有、别的表里记没记，这里看不到。";

export const isDocument = (run) => run.file?.kind === "document";
export const sourceLine = (run) => run.sources.map((s) => (s.paragraphs !== undefined ? `${s.name} ${s.paragraphs} 段 ${s.chars} 字` : `${s.name} ${s.rows} 行 ${s.fields} 列`)).join(" · ");

export const ERROR_LABELS = {
  field_unaccounted: "有字段没有去处", relation_source_mismatch: "关系写错了所在的表", relation_zero_links: "关系在数据里一条都连不上",
  relation_unknown_type: "关系指向不存在的对象", unknown_field: "引用了不存在的字段", unknown_source: "引用了不存在的表",
  empty_field: "身份字段没有值", identity_keys_mismatch: "同一对象在各表的身份键名不一致", mixed_list_identity: "身份字段混用了不同列表",
  transform_needs_single_field: "拆分规则只能用于单个身份字段", time_field_invalid: "时间字段不是日期", where_invalid: "筛选条件不成立",
  invalid_response: "返回的格式不对", model_request_failed: "模型请求失败",
};

export function validateRun(run) {
  if (!run || run.schema !== "company_ontology_run.v1" || !run.ontology || !Array.isArray(run.ontology.object_types) || !run.evaluation) {
    throw new Error("结果格式不支持：需要 company_ontology_run.v1");
  }
  return run;
}

export function checkSummary(fit) {
  if (!fit) return null;
  return { passed: fit.checks.filter((c) => c.passed).length, total: fit.checks.length };
}

export function attemptSummary(ontology) {
  const counts = new Map();
  for (const a of ontology.attempts.slice(0, -1)) for (const e of a.errors) counts.set(e.code, (counts.get(e.code) || 0) + 1);
  return { attempts: ontology.attempts.length, passed: ontology.status === "auto_built_verified", rejected: [...counts] };
}

export const typeSources = (t) => t.populated_from.map((p) => `${p.source}（${Object.values(p.identity).join(" + ")}）`).join("、");
export const typeLabel = (ontology, key) => ontology.object_types.find((t) => t.key === key)?.label || key;

export const STATUS_LABELS = { answered: "能回答", no_data: "数据里没有", ontology_gap: "本体缺这一块", query_limit: "这种问法还不支持", needs_derived: "待确认指标" };

const NUMBER = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });

/** "合计 4,631,003,200（读到 3000 个值）" — a number is never shown without saying what it was computed from. */
function measureLine(m, whole) {
  if (m.value === null) return `“${m.field}”没有一个能读成数字的值（${m.skipped} 个不是数字或为空）`;
  const read = `读到 ${m.counted} 个值${m.skipped ? `，${m.skipped} 个不是数字或为空，没算进去` : ""}`;
  return `${whole ? "全部" : `“${m.field}”`}${m.op === "sum" ? "合计" : "平均"} ${NUMBER.format(m.value)}（${read}）`;
}

/** A share as a figure, never rounded up into something it is not: 2 in 300 is 0.67%, not 1%. */
export const sharePercent = (matched, all) => (all ? (matched / all) * 100 : 0).toLocaleString("zh-CN", { maximumSignificantDigits: 2, useGrouping: false });

export function answerLines(item) {
  const a = item.answer;
  if (!a) return [];
  if (a.measure && a.groups) {
    return [...a.groups.map(([value, n, read]) => `${value}：${NUMBER.format(n)}${read === undefined ? "" : `（${read} 个值）`}`),
      ...(a.total_groups > a.groups.length ? [`另有 ${a.total_groups - a.groups.length} 组未列出`] : []),
      ...(a.unread_groups ? [`另有 ${a.unread_groups.count} 组一个能读成数字的值都没有，不算作 0，没有排进来（例如 ${a.unread_groups.examples.join("、")}）`] : []),
      ...(a.without_value ? [`${a.without_value} 个没有这个值${a.without_value_examples?.length ? `（例如 ${a.without_value_examples.join("、")}）` : ""}`] : []),
      measureLine(a.measure, true)];
  }
  if (a.measure) return [measureLine(a.measure)];
  if (a.total !== undefined) return [a.share ? `共 ${a.total} 个，其中 ${a.matched} 个“${a.share.field}”为“${a.share.equals}”（${sharePercent(a.matched, a.total)}%）` : `共 ${a.total} 个`];
  const lines = a.groups.map(([value, n, all]) => (a.share ? `${value}：${n} / ${all}（${sharePercent(n, all)}%）` : `${value}：${n}`));
  if (a.total_groups > a.groups.length) lines.push(`另有 ${a.total_groups - a.groups.length} 组未列出`);
  if (a.without_value) lines.push(`${a.without_value} 个没有这个值${a.without_value_examples?.length ? `（例如 ${a.without_value_examples.join("、")}）` : ""}`);
  return lines;
}

export const questionSummary = (round) => (round ? `能回答 ${round.answered} / ${round.total} 题` : null);

export function stabilityLines(diff) {
  const lines = [];
  const add = (label, items) => { if (items.length) lines.push(`${label}：${items.join("、")}`); };
  add("对象少了", diff.types.only_reference);
  add("对象多了", diff.types.only_ours);
  add("关系少了", diff.relations.only_reference);
  add("关系多了", diff.relations.only_ours);
  return lines;
}

export function referenceCounts(diff) {
  const { types, relations } = diff.counts;
  return `对象命中 ${types.matched} / ${types.reference}，多出 ${types.ours - types.matched} 个；关系命中 ${relations.matched} / ${relations.reference}，多出 ${relations.ours - relations.matched} 条`;
}

/** Steps shown while a build runs, derived only from the events the job reported (nothing is guessed from time). */
export function progressSteps(events, kind) {
  const doc = kind === "document";
  const steps = [
    { key: "read", label: "读取文件" },
    { key: "model", label: doc ? "逐段提取概念和关系" : "模型提出本体" },
    { key: "verify", label: doc ? "核对原文引用" : "代码核验" },
    { key: "evaluate", label: "自动评测" },
  ].map((s) => ({ ...s, status: "pending", detail: "" }));
  const at = Object.fromEntries(steps.map((s, i) => [s.key, i]));
  const mark = (key, status, detail) => { const s = steps[at[key]]; s.status = status; if (detail !== undefined) s.detail = detail; };
  let current = "model";
  for (const ev of events) {
    const d = ev.detail || {};
    if (ev.stage === "read") mark("read", "done");
    if (ev.stage === "propose") { mark("model", "active", `第 ${d.attempt} 次`); current = "model"; }
    if (ev.stage === "chunk") { mark("model", "active", `第 ${d.index} / ${d.total} 段`); current = "model"; }
    if (ev.stage === "verify") {
      mark("verify", "done", d.errors ? `第 ${d.attempt} 次退回 ${d.errors} 处问题，模型重做` : `第 ${d.attempt} 次通过`);
      if (!d.errors) mark("model", "done");
      current = d.errors ? "model" : "evaluate";
    }
    if (ev.stage === "evaluate") { mark("model", "done"); if (steps[at.verify].status === "pending") mark("verify", "done"); mark("evaluate", "active"); current = "evaluate"; }
    if (ev.stage === "questions") mark("evaluate", "active", "数据体检已完成，正在回答你在建模目的里写的问题");
    if (ev.stage === "stability") mark("evaluate", "active", "正在等另外两次建模，比对哪些每次都有");
    if (ev.stage === "done") for (const s of steps) s.status = "done";
  }
  if (!events.some((ev) => ["evaluate", "done", "failed"].includes(ev.stage)) && steps[at[current]].status === "pending") mark(current, "active");
  return steps;
}

/** What to tell the user when the local service answers with an error. A 404 means the running service predates this page. */
export function serviceError(status, data) {
  if (status === 404) return "本机建模服务是旧版本，不认识这个请求。请重启建模服务后再试。";
  return data?.error || `服务返回 ${status}`;
}

/** How a polled job ended: its run, or the words to show; null while it is still running. */
export function jobOutcome(job) {
  if (job.state === "done") return { result: job.result };
  if (job.state === "running") return null;
  return { error: job.error || "建模失败" };   // failed, or interrupted by a restart
}

/** When a job began, as the job itself reported it, so a page reopened mid-build keeps counting from there. */
export function jobStartedAt(events, now) {
  const first = Date.parse(events[0]?.at);
  return Number.isNaN(first) ? now : first;
}

/** Why the service would refuse this file, said before it is sent; "" when it is fine. */
export function fileProblem(file) {
  const suffix = (file.name.match(/\.[^.]+$/)?.[0] || "").toLowerCase();
  if (!ACCEPT.split(",").includes(suffix)) return `不支持 ${suffix || "没有扩展名的"} 文件。数据表用 .csv .xlsx，文档用 .md .txt .docx .pdf`;
  if (!file.size) return "文件是空的";
  if (file.size > 10 * 1024 * 1024) return "文件超过 10 MB";
  return "";
}

/** An ISO time from the service, shown in this machine's time zone as "MM-DD HH:mm". */
export function localTime(iso) {
  const d = new Date(iso);
  const two = (n) => String(n).padStart(2, "0");
  return `${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
}

export function previousLine(previous) {
  const when = localTime(previous.started_at);
  const purpose = previous.purpose ? `，建模目的“${previous.purpose}”` : "";
  const counts = previous.counts ? `，${previous.counts.types} 个对象、${previous.counts.relations} 条关系` : "";
  return `上一次运行：${when}${purpose}${counts}`;
}

/** Answers count objects by identity; say so when some identities disagree with themselves in the data. */
export function conflictNote(run, typeKeys) {
  const conflicts = run.evaluation.data_fit?.identity_conflicts || [];
  const parts = typeKeys.map((key) => {
    const ids = new Set(conflicts.filter((c) => c.type === key).map((c) => c.identity));
    return ids.size ? `${ids.size} 个${typeLabel(run.ontology, key)}编号` : "";
  }).filter(Boolean);
  return parts.length ? `按编号数对象：有 ${parts.join("、")}在数据里信息不一致（见数据体检），每个编号只算一次。` : "";
}

/** Identity conflicts summed by object type and field, largest first, so a thousand rows read as a few lines. */
export function conflictGroups(fit) {
  const groups = new Map();
  for (const c of fit.identity_conflicts || []) {
    const key = JSON.stringify([c.type, c.field]);
    groups.set(key, { type: c.type, field: c.field, count: (groups.get(key)?.count || 0) + 1 });
  }
  return [...groups.values()].sort((a, b) => b.count - a.count);
}

/** Why a fresh-looking result has nothing remembered against it: the system tells files apart by their content. */
export function memoryNote(run) {
  if (!run.saved_as) return "";
  const remembered = run.confirmation || run.evaluation.reference?.confirmed || run.evaluation.acceptance;
  return remembered ? "" : "这份文件还没有保存过确认或验收问题。系统按文件内容认文件：同一张表改了一行，就算另一份，上次的确认不会自动带过来。";
}

/** Keep the result in this browser. Returns "" when it is kept, or what to tell the user when it will not fit. */
export function saveResult(storage, run) {
  if (!storage) return "";   // no storage at all (a private window): the result lives in this tab, nothing to warn about
  try {
    storage.setItem(RESULT_KEY, JSON.stringify(run));
    return "";
  } catch {
    return "这次结果太大，没能存进浏览器：刷新或关掉标签页就会丢。请先下载纪要和本体和评测。";
  }
}

/** The service checks its own files against what it started with; a mismatch means edits it is not running yet. */
export const staleNote = (health) => (health?.stale
  ? "建模服务还在跑旧代码：它启动之后，后端文件改过。重启建模服务再用，不然看到的是改之前的行为。" : "");

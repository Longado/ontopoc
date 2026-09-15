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
  quotes_verified: "模型提出的每一项都能在原文里找到引用",
  no_isolated_concepts: "每个概念至少和一个别的概念有关系",
};

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

export const STATUS_LABELS = { answered: "能回答", no_data: "数据里没有", ontology_gap: "本体缺这一块", query_limit: "这种问法还不支持" };

export function answerLines(item) {
  const a = item.answer;
  if (!a) return [];
  if (a.total !== undefined) return [`共 ${a.total} 个`];
  const lines = a.groups.map(([value, n]) => `${value}：${n}`);
  if (a.total_groups > a.groups.length) lines.push(`另有 ${a.total_groups - a.groups.length} 组未列出`);
  if (a.without_value) lines.push(`${a.without_value} 个没有这个值`);
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
    if (ev.stage === "questions") mark("evaluate", "active", "数据体检已完成，正在出题并用数据回答");
    if (ev.stage === "stability") mark("evaluate", "active", "问答已完成，正在等另外两次建模，比对哪些每次都有");
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

/** Why the service would refuse this file, said before it is sent; "" when it is fine. */
export function fileProblem(file) {
  const suffix = (file.name.match(/\.[^.]+$/)?.[0] || "").toLowerCase();
  if (!ACCEPT.split(",").includes(suffix)) return `不支持 ${suffix || "没有扩展名的"} 文件。数据表用 .csv .xlsx，文档用 .md .txt .docx .pdf`;
  if (!file.size) return "文件是空的";
  if (file.size > 10 * 1024 * 1024) return "文件超过 10 MB";
  return "";
}

export function previousLine(previous) {
  const d = new Date(previous.started_at);
  const two = (n) => String(n).padStart(2, "0");
  const when = `${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`;
  const purpose = previous.purpose ? `，建模目的“${previous.purpose}”` : "";
  const counts = previous.counts ? `，${previous.counts.types} 个对象、${previous.counts.relations} 条关系` : "";
  return `上一次运行：${when}${purpose}${counts}`;
}

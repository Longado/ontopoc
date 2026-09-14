export const ACCEPT = ".csv,.xlsx";
export const DEMO_URL = "/data/demo-company-result.json";
export const RESULT_KEY = "ontopoc.studio.last-result";
export const CHECK_LABELS = {
  fields_accounted: "每个字段都有去处（用上或写明不用）",
  identity_consistent: "同一个对象在不同行里的信息不打架",
  identity_spelling: "同一个编号只有一种写法（不混用大小写、空格）",
  relations_link: "每条关系都在数据里真的连上了",
  references_resolve: "引用的对象都能在它所属的表里找到",
  sources_connected: "所有表通过共同的对象连成一片",
};

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

export const STATUS_LABELS = { answered: "能回答", no_data: "数据里没有", ontology_gap: "本体缺这一块" };

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

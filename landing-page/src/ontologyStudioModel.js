export const ACCEPT = ".csv,.xlsx";
export const DEMO_URL = "/data/demo-company-result.json";
export const RESULT_KEY = "ontopoc.studio.last-result";
export const CHECK_LABELS = {
  fields_accounted: "每个字段都有去处（用上或写明不用）",
  identity_consistent: "同一个对象在不同行里的信息不打架",
  relations_link: "每条关系都在数据里真的连上了",
  references_resolve: "引用的对象都能在它所属的表里找到",
  sources_connected: "所有表通过共同的对象连成一片",
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

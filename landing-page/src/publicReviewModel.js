export const PACK_URL = "/data/nhtsa-bolt-review-pack.json";
export const BUCKETS = {
  outside_all: "所有同类召回之外",
  covered_by_other_event: "其他同类召回已覆盖",
  inside_scope: "本召回范围内",
};
export const MARKS = { same: "同一缺陷", different: "不是", unsure: "说不清" };
export const VERDICT_TO_MARK = { yes: "same", no: "different", unknown: "unsure" };
export const ROLE_LABELS = { event: "事件", affected_object: "受影响对象", mechanism: "部件机制", signal: "信号", context: "背景" };

export function validatePack(pack) {
  if (!pack || pack.schema !== "public_review_pack.v1") throw new Error("页面数据格式不支持");
  if (pack.ontology?.status !== "auto_built_verified" || !/^[0-9a-f]{64}$/.test(pack.ontology.hash || "")) throw new Error("页面数据里的本体未通过核验");
  if (!Array.isArray(pack.recalls) || !pack.signals || typeof pack.signals !== "object") throw new Error("页面数据缺少召回或投诉");
  return pack;
}

export const storageKey = (pack) => `ontopoc.public-review.v1.${pack.ontology.hash.slice(0, 16)}`;
export const emptyState = (pack) => ({ schema: "public_review_state.v1", ontology_hash: pack.ontology.hash, confirmed_at: null, marks: {} });
export const confirmOntology = (state, now) => ({ ...state, confirmed_at: now });
const markKey = (recallId, candidateId) => `${recallId}/${candidateId}`;

export function markCandidate(state, recallId, candidateId, mark, now) {
  if (!state.confirmed_at) throw new Error("请先确认本体，再复核投诉。");
  if (!MARKS[mark]) throw new Error("复核结论只能是：同一缺陷、不是、说不清。");
  const key = markKey(recallId, candidateId);
  return { ...state, marks: { ...state.marks, [key]: { mark, note: state.marks[key]?.note || "", updated_at: now } } };
}

export function noteCandidate(state, recallId, candidateId, note, now) {
  const key = markKey(recallId, candidateId);
  if (!state.marks[key]) throw new Error("请先选择复核结论，再写备注。");
  return { ...state, marks: { ...state.marks, [key]: { ...state.marks[key], note: note.slice(0, 1000), updated_at: now } } };
}

export const markOf = (state, recallId, candidateId) => state.marks[markKey(recallId, candidateId)] || null;
export const visibleCandidates = (recall, bucket) => recall.candidates.filter((c) => c.bucket === bucket);
export const nextSelection = (selected, visible) => (visible.some((c) => c.id === selected) ? selected : visible[0]?.id || "");

export function summarize(pack, state, recallId) {
  const recall = pack.recalls.find((r) => r.id === recallId);
  let reviewed = 0, compared = 0, agree = 0;
  const disagreements = [];
  for (const c of recall.candidates) {
    const human = markOf(state, recallId, c.id)?.mark;
    if (!human) continue;
    reviewed++;
    if (!c.text_check) continue;
    compared++;
    const model = VERDICT_TO_MARK[c.text_check.verdict];
    if (model === human) agree++;
    else disagreements.push({ id: c.id, model, human });
  }
  return { total: recall.candidates.length, reviewed, compared, agree, disagreements };
}

export function restoreState(raw, pack) {
  if (raw === null) return emptyState(pack);
  const state = JSON.parse(raw);
  if (!state || state.schema !== "public_review_state.v1" || typeof state.marks !== "object" || state.marks === null) throw new Error("本机复核记录格式不支持");
  if (state.ontology_hash !== pack.ontology.hash) throw new Error("本机复核记录属于另一个本体版本");
  for (const entry of Object.values(state.marks)) {
    if (!entry || !MARKS[entry.mark] || typeof entry.note !== "string") throw new Error("本机复核记录内容有误");
  }
  return state;
}

export function exportState(pack, state, now) {
  const reviews = [];
  for (const recall of pack.recalls) {
    for (const c of recall.candidates) {
      const entry = markOf(state, recall.id, c.id);
      if (entry) reviews.push({ recall: recall.id, complaint: c.id, bucket: c.bucket, human: entry.mark, note: entry.note, model_verdict: c.text_check?.verdict || null, updated_at: entry.updated_at });
    }
  }
  return {
    schema: "public_review_export.v1", exported_at: now, ontology_hash: pack.ontology.hash,
    ontology_confirmed_at: state.confirmed_at, model: pack.run.model,
    matcher_prompt_version: pack.run.matcher_prompt_version, boundary: pack.boundary, reviews,
  };
}

export function highlight(text, evidence) {
  if (!evidence) return null;
  const index = text.indexOf(evidence);
  return index < 0 ? null : [text.slice(0, index), evidence, text.slice(index + evidence.length)];
}

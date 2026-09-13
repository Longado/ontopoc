export const PACK_URL = "/data/nhtsa-bolt-review-pack.json";
export const BUCKETS = {
  outside_all: "所有同类召回之外",
  covered_by_other_event: "其他同类召回已覆盖",
  inside_scope: "本召回范围内",
};
export const MARKS = { same: "同一缺陷", different: "不是", unsure: "说不清" };
export const VERDICT_TO_MARK = { yes: "same", no: "different", unknown: "unsure" };
export const ROLE_LABELS = { event: "事件", affected_object: "受影响对象", mechanism: "部件机制", signal: "信号", context: "背景" };

export const FLAG_LABELS = { fire: "起火", crash: "碰撞" };
const FIELD_LABELS = {
  summary: "投诉描述", dateComplaintFiled: "投诉提交日期", dateOfIncident: "事发日期", crash: "涉及碰撞", fire: "涉及起火",
  numberOfInjuries: "受伤人数", numberOfDeaths: "死亡人数", manufacturer: "制造商", vin: "车架号（前 11 位）",
  Summary: "召回摘要", Consequence: "后果", Remedy: "补救措施", Notes: "备注", ReportReceivedDate: "召回报告日期",
  Manufacturer: "制造商", parkIt: "建议停驶", parkOutSide: "建议室外停放", overTheAirUpdate: "可远程升级修复",
};
export const fieldLabel = (path) => FIELD_LABELS[path] || path;
export const displayValue = (value) => (value === "True" ? "是" : value === "False" ? "否" : value);

export function validatePack(pack) {
  if (!pack || pack.schema !== "public_review_pack.v1") throw new Error("页面数据格式不支持");
  if (pack.ontology?.status !== "auto_built_verified" || !/^[0-9a-f]{64}$/.test(pack.ontology.hash || "")) throw new Error("页面数据里的本体未通过核验");
  if (!Array.isArray(pack.recalls) || !pack.signals || typeof pack.signals !== "object") throw new Error("页面数据缺少召回或投诉");
  for (const r of pack.recalls) {
    if (!Array.isArray(r.candidates) || !Array.isArray(r.covered) || !Array.isArray(r.mechanism) || !Array.isArray(r.fields)) throw new Error(`召回 ${r.id} 的数据不完整`);
    const missing = r.candidates.find((c) => !pack.signals[c.id]);
    if (missing) throw new Error(`召回 ${r.id} 引用的投诉 ${missing.id} 不在页面数据里`);
  }
  return pack;
}

const TIMING_RANK = { after: 0, same_day: 1, before: 2 };
export function orderCandidates(candidates, signals) {
  const rank = (c) => TIMING_RANK[c.timing?.relation] ?? 3;
  return [...candidates].sort((a, b) => rank(a) - rank(b)
    || signals[b.id].flags.length - signals[a.id].flags.length
    || (signals[b.id].date || "").localeCompare(signals[a.id].date || "")
    || a.id.localeCompare(b.id));
}

export function timingLabel(timing) {
  if (!timing) return "";
  if (timing.relation === "same_day") return "召回当天";
  return timing.relation === "after" ? `召回后 ${timing.days} 天` : `召回前 ${-timing.days} 天`;
}

export function defaultRecallId(pack) {
  const pick = [...pack.recalls].sort((a, b) => Number(b.text_checked) - Number(a.text_checked) || b.counts.outside_all - a.counts.outside_all)[0];
  return pick?.id || "";
}

const seriesOf = (recall) => recall.series || recall.id;

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
  const key = seriesOf(recall);
  let reviewed = 0, compared = 0, agree = 0;
  const disagreements = [];
  for (const c of recall.candidates) {
    const human = markOf(state, key, c.id)?.mark;
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
  const seen = new Set();
  for (const recall of pack.recalls) {
    const key = seriesOf(recall);
    for (const c of recall.candidates) {
      const entry = markOf(state, key, c.id);
      if (!entry || seen.has(`${key}/${c.id}`)) continue;
      seen.add(`${key}/${c.id}`);
      const signal = pack.signals[c.id] || {};
      reviews.push({
        recall: key, complaint: c.id, bucket: c.bucket, human: entry.mark, note: entry.note,
        model_verdict: c.text_check?.verdict || null, updated_at: entry.updated_at,
        vehicles: signal.objects || [], parts: signal.parts || [], complaint_date: signal.date ?? null, flags: signal.flags || [],
        recall_date: recall.date ?? null, timing: c.timing?.relation ?? null, days_from_recall: c.timing?.days ?? null,
        via_alias: Boolean(c.via_alias), series_recalls: pack.recalls.filter((r) => seriesOf(r) === key).map((r) => r.id),
      });
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

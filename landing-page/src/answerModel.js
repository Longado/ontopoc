// How an answer that cannot be given says why, and what a derived measure waiting for the person shows.

// A reason the model wrote is its reasoning, not a finding: the page says one fixed plain sentence per status and
// keeps the model's words one click away. A reason code found is short and exact, so it stands as it is.
const MODEL_SAYS = {
  query_limit: "本体里需要的都有，但现在的查询还算不了这种问法。",
  ontology_gap: "回答它需要的对象、关系或字段，本体里还没有。",
  no_data: "本体里有这一块，但数据里没有能回答它的行。",
};

export function reasonView(item) {
  if (item.status === "answered" || !item.reason) return null;
  if (!item.reason_from_model) return { line: item.reason, detail: null };
  return { line: MODEL_SAYS[item.status] || "现在答不了。", detail: item.reason };
}

const count = (n) => n.toLocaleString("zh-CN");

export function derivedCard(item, typeLabel) {
  const { label, formula, preview } = item.derive;
  return {
    formula: `${label} = ${formula}`,
    tried: `在全部${typeLabel}上试算：算出 ${count(preview.counted)} 个${preview.skipped ? `，${count(preview.skipped)} 个算不了` : ""}`,
    examples: preview.examples.map((e) => `${e.name} → ${count(e.value)}`),
    skipped: preview.skipped_examples,
  };
}

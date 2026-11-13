/** The data view and the ask box: what was uploaded, how it hangs together, and what to ask of it. */

/** One sentence per column that would connect tables the ontology left apart. */
export function bridgeLines(run) {
  return (run.evaluation?.data_fit?.bridges || []).map((b) =>
    `${b.from_source} 的「${b.from_field}」有 ${b.linked_rows} / ${b.rows} 行，能在 ${b.to_source} 的「${b.to_field}」里找到`);
}

const DROPPED = { blank: "空行", title: "标题行" };
const sampleText = (s) => `${Object.values(s.key).join(" + ")}（${s.count} 行）`;

/** What the data checks found for one uploaded table: rows in the file, stored and dropped (with the reason), and one
 *  line per drafted identity saying whether its columns are unique, or, for a column that only names objects another
 *  table describes, how many different values it holds. Null for a run saved before the checks existed. */
export function tableChecks(run, name) {
  const found = run.data_checks;
  const table = found?.tables?.find((t) => t.dataset === name);
  if (!table) return null;
  const labels = Object.fromEntries((run.ontology?.object_types || []).map((t) => [t.key, t.label || t.key]));
  const dropped = Object.entries(table.dropped || {}).map(([reason, n]) => `${DROPPED[reason] || reason} ${n}`);
  return {
    rowsIn: table.rows_in, rowsStored: table.rows_stored, error: table.error || null,
    droppedCount: Object.values(table.dropped || {}).reduce((a, b) => a + b, 0), dropped: dropped.join("、"),
    keys: found.keys.filter((k) => k.dataset === name).map((k) => {
      const cols = k.key_columns.join(" + ");
      const empty = k.null_key_rows ? `${k.null_key_rows} 行没有值` : "";
      const parts = k.check_type === "key_distinct"
        ? [`${k.distinct} 个不同取值`, empty].filter(Boolean)
        : [k.violations ? `重复 ${k.violations} 行，如 ${k.samples.slice(0, 3).map(sampleText).join("、")}` : "", empty].filter(Boolean);
      return { type: labels[k.object_type] || k.object_type, columns: cols, checkId: k.check_id, failed: k.status === "failed",
               text: parts.length ? parts.join("，") : "没有重复，没有空值" };
    }),
  };
}

const CARDINALITY = { one_to_one: "一对一", many_to_one: "多对一", one_to_many: "一对多", many_to_many: "多对多" };
const fanoutLine = (s, rule) => {
  const repeats = `「${s.lookup}」表里 ${s.fanout.keys} 个编号重复（${keysText(s.fanout.samples, s.fanout.keys)}）`;
  if (rule?.rule === "keep_latest") return { text: `${repeats}，已按你的选择只留最新的一行，连过去不再多出行`, warn: false };
  if (rule?.rule === "data_error") return { text: `${repeats}，已标为数据错误，等客户改数据`, warn: true };
  const extra = `${s.fanout.source_rows} 行连过去会多出 ${s.fanout.extra_rows} 行`;
  return { text: `${repeats}，${rule?.rule === "keep_both" ? `你选了每一行都留，${extra}` : extra}`, warn: true };
};
const keysText = (samples, distinct) => `${samples.map((s) => s.key).join("、")}${distinct > samples.length ? " 等" : ""}`;

/** What the relation check found for each relation, one line per finding ({ text, warn }), warn when it is a problem: rows whose key
 *  the describing table does not have (with the keys), keys that repeat there (a join would add rows), a declared cardinality the rows
 *  break. `match` picks the relations (by key or by source table); null when the run has no relation check. The repeats are counted
 *  on the table as stored; `rules` ({"<object type>.<table>": the rule a person chose}) says what became of them. */
export function relationLines(run, match, rules = {}) {
  const found = run.data_checks?.relations;
  if (!found) return null;
  const label = Object.fromEntries((run.ontology?.object_types || []).map((t) => [t.key, t.label || t.key]));
  return found.filter(match).map((r) => ({
    key: r.key, source: r.source,
    lines: [
      ...r.sides.flatMap((s) => [
        { text: `「${s.columns.join(" + ")}」在「${s.lookup}」表里：${(s.matched).toLocaleString("zh-CN")} / ${(s.rows - s.empty).toLocaleString("zh-CN")} 行找到对应`, warn: false },
        ...(s.unmatched ? [{ text: `${s.unmatched} 行找不到（${keysText(s.samples, s.unmatched_keys)}）${s.if_trimmed ? `，其中 ${s.if_trimmed} 行去掉空格、不分大小写后能对上` : ""}`, warn: true }] : []),
        ...(s.empty ? [{ text: `${s.empty} 行的编号是空的，没算`, warn: false }] : []),
        ...(s.fanout.keys ? [fanoutLine(s, rules[`${s.object}.${s.lookup}`])] : []),
      ]),
      ...(r.cardinality.declared ? [{ warn: !r.cardinality.holds, text: r.cardinality.holds ? `声明的基数「${CARDINALITY[r.cardinality.declared]}」成立`
        : `声明的基数「${CARDINALITY[r.cardinality.declared]}」不成立：一个${label[r.from] || r.from}最多连 ${r.cardinality.most_from} 个${label[r.to] || r.to}，一个${label[r.to] || r.to}最多连 ${r.cardinality.most_to} 个${label[r.from] || r.from}` }] : []),
    ],
  }));
}

/** {"table.column": "名字说是中位数，算出来是平均数"} for the columns whose name does not say what the rows give (open items of that kind):
 *  also the ones that are right over a confirmed view ("按「有效订单」算的合计") and the ones that could not choose a source table. */
export function nameNotes(items) {
  const note = (i) => {
    if (i.kind === "name_by_view") return `按「${i.column.view}」算的${i.column.says_text}`;
    if (i.kind === "name_values") return `名字说是${i.column.says_text}，有值不是数字，没和重算比`;
    if (i.kind === "name_source") return `名字说是${i.column.says_text}，${i.column.candidates.length} 张表都能重算，还没定用哪一张`;
    return `名字说是${i.column.says_text}，${i.column.actual_text ? `算出来是${i.column.actual_text}` : "重算对不上"}${i.column.how ? `（${i.column.how}）` : ""}`;
  };
  return Object.fromEntries((items || []).filter((i) => ["name_vs_calc", "name_by_view", "name_source", "name_values"].includes(i.kind)).map((i) => [`${i.column.source}.${i.column.column}`, note(i)]));
}

const who = (rule) => (rule.confirmed_by ? `（${rule.confirmed_by}）` : "");
/** What the column could not settle: keys whose rows share the latest value (the later row of the file was taken) or have none. */
const unsaid = (rule) => [rule.ties ? `${rule.ties} 个编号的几行在这一列上并列，取了文件里靠后的一行` : "", rule.blank ? `${rule.blank} 个编号有的行这一列是空的，按最旧算` : ""].filter(Boolean).map((t) => `；${t}`).join("");
const RULE_SAYS = {
  keep_both: () => "每一行都留",
  keep_latest: (rule) => `只留「${rule.column}」最新的一行${unsaid(rule)}`,
  data_error: () => "当作数据错误，等客户改数据",
};

/** Rows that carry an identity an earlier row of the same table already had, and what a person decided to do about them. */
export function repeatLines(identityRepeats = []) {
  return identityRepeats.filter((r) => r.repeated > 0).map((r) =>
    `${r.source}表：${r.rows.toLocaleString("zh-CN")} 行，${r.identities.toLocaleString("zh-CN")} 个不同编号，${r.repeated} 行是重复编号${r.examples?.length ? `（${r.examples.join("、")}）` : ""}。`
    + (r.rule ? `已确认${who(r.rule)}：${RULE_SAYS[r.rule.rule](r.rule)}` : "还没定怎么算，重复的每一行都列在下面"));
}

/** The object list's count, with where each number comes from: objects the graph has, the ones only other tables name, rows listed. */
export function objectCountLine(page) {
  const { objects, total, mentioned_only: only } = page;
  const tables = (page.identity_repeats || []).map((r) => r.source);
  const from = only?.count ? `：${objects - only.count} 个在${tables.join("、")}表里有行，${only.count} 个只在别的表里出现${only.examples?.length ? `（${only.examples.join("、")}）` : ""}` : "";
  return `共 ${objects.toLocaleString("zh-CN")} 个对象${from}${total !== objects ? `；列出 ${total.toLocaleString("zh-CN")} 行，重复的编号各占一行` : ""}`;
}

const MARK_SAYS = { pending: () => "还没定怎么算", keep_both: () => "每一行都留", data_error: () => "当作数据错误", keep_latest: (m) => `按「${m.column}」只留最新的一行${m.tie ? "（这一列上并列，取了文件里靠后的一行）" : ""}${m.blank ? "（有一行这一列是空的，按最旧算）" : ""}` };

/** What the list says beside a row of a repeated key. */
export const repeatMark = (mark) => (mark ? `重复编号（共 ${mark.rows} 行），${MARK_SAYS[mark.repeat](mark)}` : "");

/** Every uploaded table with its size, skipped title lines, column shapes (null for runs saved before these were
 *  kept) and the connected group it belongs to. */
export function layoutTables(run) {
  const groups = run.evaluation?.data_fit?.source_groups || [];
  const profiled = Object.fromEntries((run.evaluation?.handover?.sources || []).map((s) => [s.name, s]));
  return run.sources.map((s) => ({
    name: s.name, rows: s.rows, fieldCount: s.fields,
    skipped: profiled[s.name]?.skipped_rows || s.skipped_rows || [],
    fields: profiled[s.name]?.fields || null,
    group: Math.max(0, groups.findIndex((g) => g.includes(s.name))),
    checks: tableChecks(run, s.name),
  }));
}

/** Questions this run already answered, as starting points: clicking one shows its answer, no model call. */
export function askSuggestions(run) {
  return (run.evaluation?.questions?.items || []).filter((i) => i.status === "answered").slice(0, 3);
}

/** The questions asked in the box, each once as it stands now: asking again or working out again adds a round, and only
 *  the last answer to a question counts. */
export function askedNow(run) {
  const latest = new Map();
  for (const round of run.evaluation?.asked || []) for (const item of round.items || []) latest.set(item.question ?? item, item);
  return [...latest.values()];
}

/** The last question asked in the box, or the error it ended with. */
export function latestAsked(run) {
  const last = (run.evaluation?.asked || []).at(-1);
  if (!last) return null;
  return last.error ? { error: last.error } : last.items.at(-1) || null;
}

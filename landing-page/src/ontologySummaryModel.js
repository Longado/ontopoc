// A page the consultant can hand over: what was read, what the ontology says, what a person confirmed, what to check.
// Only what is already on screen goes in here — no model prose, no internal keys, and no claim nobody has checked.
import { ACCEPTANCE_LABELS } from "./ontologyAcceptanceModel.js";
import { CHECK_LABELS, answerLines, isDocument, localTime, typeLabel } from "./ontologyStudioModel.js";

const name = (ontology, key) => typeLabel(ontology, key);
const SHOWN = 10;   // a handover page, not a data dump: the rest is in the JSON beside it

export function summaryMarkdown(run) {
  const { ontology, evaluation } = run;
  const fit = evaluation.data_fit || evaluation.document_fit;
  const confirmed = run.confirmation;
  const out = [`# ${run.file.name} 本体摸底纪要`, "", `建模目的：${run.purpose}`, `建模时间：${localTime(run.started_at)}`, ""];

  out.push("## 读了什么", "");
  out.push(...run.sources.map((s) => (s.paragraphs !== undefined ? `- ${s.name}（${s.paragraphs} 段 ${s.chars} 字）` : `- ${s.name}（${s.rows} 行 ${s.fields} 列）`)), "");

  // once a person has judged the ontology, the body states only what they judged right, under the names they gave;
  // what they judged wrong or have not judged is set apart, so a reader cannot take the model's proposal for theirs
  const verdict = (kind, key) => (confirmed ? confirmed.decisions[kind][key]?.verdict || null : "ok");
  const called = (key) => confirmed?.decisions.types[key]?.label || name(ontology, key);
  const typeLine = (t) => `${called(t.key)}${t.definition ? `：${t.definition}` : ""}`;
  const relationLine = (r) => `${called(r.from)} ${r.label || "→"} ${called(r.to)}`;
  const pick = (items, kind, v) => items.filter((x) => verdict(kind, x.key) === v);
  out.push("## 业务里有哪些东西", "");
  if (!confirmed) out.push("以下都是模型提出的，还没有人确认。", "");
  out.push(...pick(ontology.object_types, "types", "ok").map((t) => `- ${typeLine(t)}`), "");
  const related = pick(ontology.relations, "relations", "ok");
  if (related.length) {
    out.push("它们怎么关联：", "");
    out.push(...related.map((r) => `- ${relationLine(r)}${r.meaning ? `（${r.meaning}）` : ""}`), "");
  }
  if (confirmed) {
    const aside = (v) => [pick(ontology.object_types, "types", v).map((t) => called(t.key)).join("、"), pick(ontology.relations, "relations", v).map(relationLine).join("；")].filter(Boolean).join("；");
    if (confirmed.decisions.added.length) out.push(`确认时补上的：${confirmed.decisions.added.join("、")}`, "");
    if (aside("wrong")) out.push(`确认时判错、没有列进来：${aside("wrong")}`, "");
    if (aside(null)) out.push(`还没判的，是模型提出的：${aside(null)}`, "");
  }

  if (fit) {
    const failed = fit.checks.filter((c) => !c.passed);
    out.push("## 数据体检", "", "以下由代码在上传的数据上逐行算，不经过模型。", "", failed.length ? `${fit.checks.length} 项检查里 ${failed.length} 项没通过：` : `${fit.checks.length} 项检查全部通过。`, "");
    out.push(...failed.map((c) => `- 未通过：${CHECK_LABELS[c.key] || c.key}`));
    for (const c of (fit.identity_conflicts || []).slice(0, 5)) {
      out.push(`- ${name(ontology, c.type)} ${c.identity} 的“${c.field}”在不同行里写了 ${c.values.join(" / ")}`);
    }
    for (const m of fit.missing_across_sources || []) {
      out.push(`- ${name(ontology, m.type)}：${m.count} 个被引用但在“${m.source}”里找不到，例如 ${m.examples.join("、")}`);
    }
    const idOnly = fit.id_only || [];
    if (idOnly.length) {
      out.push("", "下面这些对象只有编号、没有描述它的表。它们能用来分组统计，但这份数据里没有任何一张表在说它们是什么：", "");
      out.push(...idOnly.map((t) => `- ${name(ontology, t.type)}：${t.count} 个编号，来自“${t.source}”的“${t.field}”，这份数据里没有一张表在描述它`));
    }
    out.push("", "这些结论只覆盖上面列出的文件，别的系统里有没有、别的表里记没记，这里看不到。", "");
  }

  const acceptance = evaluation.acceptance;
  if (acceptance) {
    out.push("## 验收问题（和业务方说定的）", "", "问题和口径是人定的；答案由代码在上传的数据上算，不经过模型。", "");
    for (const item of acceptance.items) {
      out.push(`### ${item.question}`, "");
      if (item.note) out.push(`口径：${item.note}`, "");
      out.push(`结果：${ACCEPTANCE_LABELS[item.status] || item.status}${item.changed === null ? "" : item.changed ? "，和上次不一样" : "，和上次一致"}`, "");
      const lines = answerLines(item);
      const listed = item.answer?.groups?.length || 0;   // group lines come first; what follows says what the figures leave out
      out.push(...lines.slice(0, Math.min(listed, SHOWN)).map((line) => `- ${line}`));
      if (listed > SHOWN) out.push(`- 另有 ${listed - SHOWN} 组，完整结果见“本体和评测”文件`);
      out.push(...lines.slice(listed).map((line) => `- ${line}`));   // never cut: how many values were read, skipped, or unreadable
      out.push("");
      if (item.path) out.push(`怎么算的：${item.path}`, "");
    }
  }

  out.push("## 谁确认过", "");
  if (!confirmed) {
    out.push("还没有人逐项确认，以上都是模型的草稿，不能当结论。", "");
  } else {
    const verdicts = (kind) => Object.values(confirmed.decisions[kind]).filter((d) => d.verdict === "ok").length;
    const wrong = [...Object.values(confirmed.decisions.types), ...Object.values(confirmed.decisions.relations)].filter((d) => d.verdict === "wrong").length;
    out.push(`${confirmed.confirmed_by ? `${confirmed.confirmed_by}，` : ""}${localTime(confirmed.confirmed_at)} 逐项确认：判对 ${verdicts("types")} 个对象、${verdicts("relations")} 条关系`
      + `${wrong ? `，判错 ${wrong} 项` : ""}${confirmed.decisions.added.length ? `，补了 ${confirmed.decisions.added.join("、")}` : ""}。`, "");
    const renames = Object.entries(confirmed.decisions.types).filter(([, d]) => d.label).map(([key, d]) => `- 改名：${name(ontology, key)} 改成“${d.label}”`);
    if (renames.length) out.push("确认时改过的名字（正文用的是改后的名字）：", "", ...renames, "");
  }

  if (ontology.data_gaps.length) {
    out.push("## 模型指出的数据缺口", "");
    out.push(...ontology.data_gaps.map((g) => `- ${g}`), "");
  }

  out.push("---", "", `本文由 OntoPoc 从${isDocument(run) ? "上传的文档" : "上传的数据表"}生成，每一条都能在页面上找到出处：对象和关系在“看本体”，体检在“看评测 / 数据体检”，验收问题在“看评测 / 业务问答”。`);
  return out.join("\n");
}

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

  out.push("## 业务里有哪些东西", "");
  out.push(...ontology.object_types.map((t) => `- ${t.label || t.key}${t.definition ? `：${t.definition}` : ""}`), "");
  if (ontology.relations.length) {
    out.push("它们怎么关联：", "");
    out.push(...ontology.relations.map((r) => `- ${name(ontology, r.from)} ${r.label || "→"} ${name(ontology, r.to)}${r.meaning ? `（${r.meaning}）` : ""}`), "");
  }

  if (fit) {
    const failed = fit.checks.filter((c) => !c.passed);
    out.push("## 数据体检", "", failed.length ? `${fit.checks.length} 项检查里 ${failed.length} 项没通过：` : `${fit.checks.length} 项检查全部通过。`, "");
    out.push(...failed.map((c) => `- 未通过：${CHECK_LABELS[c.key] || c.key}`));
    for (const c of (fit.identity_conflicts || []).slice(0, 5)) {
      out.push(`- ${name(ontology, c.type)} ${c.identity} 的“${c.field}”在不同行里写了 ${c.values.join(" / ")}`);
    }
    for (const m of fit.missing_across_sources || []) {
      out.push(`- ${name(ontology, m.type)}：${m.count} 个被引用但在“${m.source}”里找不到，例如 ${m.examples.join("、")}`);
    }
    out.push("", "这些结论只覆盖上面列出的文件，别的系统里有没有、别的表里记没记，这里看不到。", "");
  }

  const acceptance = evaluation.acceptance;
  if (acceptance) {
    out.push("## 验收问题（和业务方说定的）", "");
    for (const item of acceptance.items) {
      out.push(`### ${item.question}`, "");
      if (item.note) out.push(`口径：${item.note}`, "");
      out.push(`结果：${ACCEPTANCE_LABELS[item.status] || item.status}${item.changed === null ? "" : item.changed ? "，和上次不一样" : "，和上次一致"}`, "");
      const lines = answerLines(item);
      out.push(...lines.slice(0, SHOWN).map((line) => `- ${line}`));
      if (lines.length > SHOWN) out.push(`- 另有 ${lines.length - SHOWN} 组，完整结果见“本体和评测”文件`);
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
    if (renames.length) out.push("确认时改过的名字（纪要正文用的是模型给的名字）：", "", ...renames, "");
  }

  if (ontology.data_gaps.length) {
    out.push("## 模型指出的数据缺口", "");
    out.push(...ontology.data_gaps.map((g) => `- ${g}`), "");
  }

  out.push("---", "", `本文由 OntoPoc 从${isDocument(run) ? "上传的文档" : "上传的数据表"}生成，每一条都能在页面上找到出处：对象和关系在“看本体”，体检在“看评测 / 数据体检”，验收问题在“看评测 / 业务问答”。`);
  return out.join("\n");
}

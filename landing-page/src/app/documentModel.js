// The words of the Documents page and of an answer from documents, as plain functions of what the service sends (document_answers.py).
import { timeText } from "./format.js";
import { t } from "./i18n/index.js";

export const DOC_KINDS = [".md", ".txt", ".docx", ".pdf"];   // what company_documents reads
export const DOC_ACCEPT = DOC_KINDS.join(",");

/** A document's own page. */
export const documentHref = (id) => `#/documents/${encodeURIComponent(id)}`;

/** Why this file cannot be sent ("" when it can): a kind the service does not read, or an empty file. The service checks again. */
export function docFileProblem(file) {
  if (!file || !file.size) return t("documents.file.empty");
  const name = String(file.name ?? "").toLowerCase();
  return DOC_KINDS.some((k) => name.endsWith(k)) ? "" : t("documents.file.kind", { kinds: DOC_KINDS.join(" / ") });
}

/** One document in the list: its state, a line of what it holds, who put it forward or confirmed it, and who can confirm it while it waits. */
export function documentLine(d, { mayBuild = false } = {}) {
  const count = Array.isArray(d.passages) ? d.passages.length : d.passages;   // a document's own page holds the passages themselves
  const meta = [t("documents.passages", { count }), t("documents.version", { version: d.version }), ...(d.builders_only ? [t("documents.buildersOnly")] : [])].join(" · ");
  const by = d.state === "confirmed" && d.confirmed_by ? t("documents.confirmedBy", { by: d.confirmed_by, when: d.confirmed_at ? timeText(d.confirmed_at) : "" }).trim()
    : d.proposed_by ? t("documents.proposedBy", { by: d.proposed_by }) : "";
  const who = d.state === "confirmed" || !d.who_can_confirm ? "" : d.who_can_confirm.length ? t("documents.whoCanConfirm", { names: d.who_can_confirm.join(t("ask.sep")) }) : t("documents.nobodyCanConfirm");
  return { id: d.id, name: d.name, state: d.state, meta, by, who, held: d.held ?? "", mayConfirm: Boolean(d.may_confirm) && d.state !== "confirmed", href: documentHref(d.id),
    reason: d.reason ? t("documents.sentBackWhy", { reason: d.reason }) : "",   // sent back: why (a builder's view; a viewer never sees one that waits)
    maySendBack: mayBuild && d.state === "confirmed", mayRemove: mayBuild };
}

/** A removed document, as builders see it in the list: its name, who removed it, when and why. The service never sends these to a viewer. */
export function removedLine(r) {
  return { name: r.name, text: t("documents.removedBy", { by: r.removed_by ?? "", when: r.removed_at ? timeText(r.removed_at) : "", reason: r.reason }) };
}

/** An answer from confirmed documents: the service's line (the documents' own words, chosen by the assistant, not from the data) and each quote with where it
 * comes from. There is no sentence of the model's own to show. null for anything else: an answer from the data, a refusal, or the line that the documents say
 * nothing (which rides in the refusal's own sentence). */
export function answerFromDocuments(record) {
  if (record?.status !== "from_documents" || !Array.isArray(record.documents?.quotes)) return null;
  return {
    line: record.documents.line,
    quotes: record.documents.quotes.map((q, i) => ({ key: `q-${i}`, quote: q.quote, parts: sentenceParts(q), source: t("ask.documents.source", { name: q.document, where: q.where }), href: documentHref(q.document_id) })),
  };
}

/** [before, the quoted part, after] of the sentence that holds a quote, as the service sends them (three strings: no offsets to count); the quote alone when no
 * sentence came with it (a kept answer from before). */
export function sentenceParts(q) {
  const s = q.sentence;
  if (!s || typeof s !== "object" || typeof s.quote !== "string") return ["", q.quote, ""];
  return [String(s.before ?? ""), s.quote, String(s.after ?? "")];
}

const grouped = (n) => Number(n).toLocaleString("en-US");

/** The limits, as the page states them. */
export const limitsText = (l) => t("documents.limits", { passage: grouped(l.passage_chars), passages: l.passages_to_model, chars: grouped(l.max_chars), docs: l.max_documents });

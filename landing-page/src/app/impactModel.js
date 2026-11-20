// What a change does to the board numbers (POST /api/workspace/impact, the upload preview's `boards`) and the receipt after it (POST /api/workspace/receipt), as words.
// The service works every number out (change_preview, workspace_receipt); this only words them for the table and writes the Markdown a person copies.
import { formatNumber, t } from "./i18n/index.js";
import { timeText } from "./format.js";

const KINDS = ["type", "meaning", "relation", "view", "derived", "action", "pipeline"];
const STATES = ["confirmed", "checked", "proposed", "needs_look", "rejected"];

const number = (n) => formatNumber(n, { maximumFractionDigits: 2 });
const kindWord = (kind) => (KINDS.includes(kind) ? t(`review.kind.${kind}`) : kind);
const versionsText = (on) => Object.entries(on ?? {}).map(([name, v]) => t("review.receipt.version", { name, version: v })).join(t("review.receipt.sep"));
const cell = (text) => String(text ?? "").replace(/\|/g, "\\|").replace(/\s*\n\s*/g, " ");

/** One side of a card (now, or after): {text, note, grey, refused}. A card that refuses says so, with its reason as the note; a grey one says why. */
export function figureCell(fig) {
  if (!fig) return { text: "—", note: "", grey: false, refused: false };
  if (fig.status !== "ok") return { text: t("review.impact.refused"), note: fig.text ?? "", grey: false, refused: true };
  const text = fig.value != null ? number(fig.value) : fig.text;
  const groups = fig.value != null && fig.text && fig.text !== text && !/^[\d,.\s-]+$/.test(fig.text) ? fig.text : "";   // a chart's groups beside its total
  return { text, note: fig.grey ? fig.why || t("review.impact.grey") : groups, grey: Boolean(fig.grey), refused: false };
}

/** How a card moves, in words: {text, level} where level is up, down, refuses, opens, grey or same. */
export function changeCell(change) {
  if (!change) return { text: "", level: "same" };
  if (change.kind === "number") return { text: `${change.delta > 0 ? "+" : "−"}${number(Math.abs(change.delta))}`, level: change.delta > 0 ? "up" : "down" };
  const level = { refuses: "refuses", opens: "opens", grey: "grey", confirmed: "opens", other: "up" }[change.kind] ?? "same";
  return { text: t(`review.impact.change.${["refuses", "opens", "grey", "confirmed", "other"].includes(change.kind) ? change.kind : "same"}`), level };
}

const movedText = (moved, key = "review.impact.movedOne") => (moved ?? []).map((m) => t(key, { name: m.name, from: m.from, to: m.to })).join(t("review.receipt.sep"));

/** What new data since the last confirmation means here, in one or two sentences: `accepted` moves (the data sent the item back; confirming lets the new data's numbers
 * count) and the others (the item stayed confirmed through the new data; the table shows only the change). `words` is review.impact or review.receipt. */
function movedSentences(moved, words) {
  const one = words === "review.impact" ? "review.impact.movedOne" : "review.receipt.movedOne";
  const accepted = (moved ?? []).filter((m) => m.accepted);
  const kept = (moved ?? []).filter((m) => !m.accepted);
  return [
    ...(accepted.length ? [t(`${words}.dataAccepted`, { list: movedText(accepted, one) })] : []),
    ...(kept.length ? [t(`${words}.dataMoved`, { list: movedText(kept, one) })] : []),
  ].join(" ");
}

/** A receipt item's new data, as its line says it. */
export const movedLine = (moved) => movedSentences(moved, "review.receipt");

/** The elements a group confirmation confirmed ({confirmed: [{element, title}]}): what its receipt is asked for. */
export const receiptElements = (result) => (result?.confirmed ?? []).map((c) => c.element);

/** The table and the sentences around it: {rows: [{key, board, card, now, after, change}], sentence, capped, answers, refused, dataMoved}. `done`: the change is made (a
 * receipt). `dataMoved` says that a dataset has a newer version than the one the definition was last confirmed on, and whether confirming accepts it. */
export function impactView(impact, done = false) {
  if (!impact) return { rows: [], sentence: "", capped: "", answers: "", refused: "", dataMoved: "" };
  if (impact.refused) return { rows: [], sentence: t("review.impact.refusedSentence", { why: impact.refused }), capped: "", answers: "", refused: impact.refused, dataMoved: "" };
  const rows = (impact.cards ?? []).map((c) => ({ key: `${c.board.id}/${c.card.id}`, board: c.board.name, card: c.card.title, now: figureCell(c.now), after: figureCell(c.after), change: changeCell(c.change) }));
  const moving = rows.filter((r) => r.change.level !== "same").length;
  const boards = new Set((impact.cards ?? []).map((c) => c.board.id)).size;
  const words = done ? "review.receipt" : "review.impact";
  const sentence = !rows.length || !moving ? t(`${words}.none`, { boards: impact.checked?.boards ?? 0 }) : t(`${words}.some`, { count: moving, boards });
  const checked = impact.checked ?? {};
  const capped = checked.capped ? t("review.impact.capped", { cards: checked.cards, left: checked.left }) : "";
  const mine = impact.answers?.mine ?? [];
  const others = impact.answers?.others ?? 0;
  const answers = mine.length || others ? t("review.impact.answers", { mine: mine.length, others }) + (mine.length ? t("review.impact.yours", { list: mine.map((a) => t("review.receipt.quoted", { text: a.question })).join(t("review.receipt.sep")) }) : "") : "";
  const dataMoved = movedSentences(impact.data_moved, "review.impact");
  return { rows, sentence, capped, answers, refused: "", dataMoved };
}

/** Whether the person should be shown the table before going on: a card moves, or the change would be refused. */
export const impactMatters = (impact) => Boolean(impact && (impact.refused || (impact.cards ?? []).some((c) => c.change?.kind !== "same")));

/** The receipt after a confirmation, as Markdown to copy: what changed, who proposed and who confirmed it, on which data version, the board numbers from and to,
 * the cards that now refuse, the saved answers that used it. */
export function receiptMarkdown(receipt) {
  const lines = [`## ${t("review.receipt.title")}`, "", t("review.receipt.at", { at: timeText(receipt.at) }), "", `### ${t("review.receipt.what")}`];
  for (const item of receipt.items ?? []) {
    lines.push(`- ${t("review.receipt.named", { kind: kindWord(item.kind), title: item.title })}`);
    lines.push(`  - ${item.before != null ? t("review.receipt.before", { text: item.before }) : t("review.receipt.first")}`);
    lines.push(`  - ${t("review.receipt.after", { text: item.after })}`);
    lines.push(`  - ${t("review.receipt.who", { proposed: item.proposed_by ?? t("review.group.unknown"), confirmed: item.confirmed_by ?? t("review.group.unknown"), at: timeText(item.confirmed_at) })}`);
    lines.push(`  - ${t("review.receipt.on", { on: versionsText(item.on) || "—" })}`);
    if (item.data_moved?.length) lines.push(`  - ${movedSentences(item.data_moved, "review.receipt")}`);
    if (item.evidence) lines.push(`  - ${t("review.receipt.evidence", { ref: item.evidence })}`);
  }
  const view = impactView(receipt);
  const moved = view.rows.filter((r) => r.change.level !== "same");
  lines.push("", `### ${t("review.receipt.numbers")}`);
  if (!moved.length) lines.push(t("review.receipt.noNumbers"));
  else {
    lines.push(`| ${t("review.impact.board")} | ${t("review.impact.card")} | ${t("review.receipt.from")} | ${t("review.receipt.to")} | ${t("review.impact.change")} |`, "|---|---|---:|---:|---|");
    for (const r of moved) lines.push(`| ${cell(r.board)} | ${cell(r.card)} | ${cell(r.now.text)} | ${cell(r.after.text)}${r.after.grey ? ` ${t("review.receipt.greyMark")}` : ""} | ${cell(r.change.text)} |`);
  }
  const refusing = (receipt.cards ?? []).filter((c) => c.after?.status !== "ok");
  if (refusing.length) {
    lines.push("", `### ${t("review.receipt.refusing")}`);
    for (const c of refusing) lines.push(`- ${c.board.name} · ${c.card.title}${t("review.receipt.colon")}${c.after.text}`);
  }
  if (view.answers) lines.push("", view.answers);
  if (view.capped) lines.push("", view.capped);
  return lines.join("\n") + "\n";
}

/** The workspace summary: one line per kind with its states, then the checks, the rows the confirmed types read, and who confirmed what on which version. */
export function summaryView(summary) {
  const kinds = KINDS.filter((k) => summary.definitions?.[k]).map((k) => ({
    kind: kindWord(k),
    states: STATES.filter((s) => summary.definitions[k][s]).map((s) => t("review.summary.state", { state: t(`review.summary.states.${s}`), count: summary.definitions[k][s] })).join(t("review.receipt.sep")),
  }));
  const checks = t("review.summary.checks", { passed: summary.checks?.passed ?? 0, failed: summary.checks?.failed ?? 0, error: summary.checks?.error ?? 0 });
  const rows = summary.rows
    ? t("review.summary.rows", { covered: number(summary.rows.covered), total: number(summary.rows.total), datasets_covered: summary.rows.datasets_covered, datasets: summary.rows.datasets })
    : t("review.summary.rowsHidden");
  const needs = Object.entries(summary.needs_look ?? {}).map(([word, n]) => `${word} ${n}`).join(t("review.receipt.sep"));
  const who = (summary.confirmations ?? []).map((c) => ({ key: c.element, what: t("review.receipt.named", { kind: kindWord(c.kind), title: c.title }), by: c.by ?? t("review.group.unknown"), at: timeText(c.at), on: versionsText(c.on) || "—" }));
  return { kinds, checks, rows, needs: needs ? t("review.summary.needs", { list: needs }) : "", who };
}

export function summaryMarkdown(summary) {
  const v = summaryView(summary);
  const lines = [`## ${t("review.summary.title")}`, "", t("review.receipt.at", { at: timeText(summary.at) }), "", `### ${t("review.summary.definitions")}`];
  for (const k of v.kinds) lines.push(`- ${k.kind}${t("review.receipt.colon")}${k.states}`);
  if (v.needs) lines.push(`- ${v.needs}`);
  lines.push(`- ${v.checks}`, `- ${v.rows}`);
  if (v.who.length) {
    lines.push("", `### ${t("review.summary.who")}`, `| ${t("review.summary.colWhat")} | ${t("review.summary.colBy")} | ${t("review.summary.colAt")} | ${t("review.summary.colOn")} |`, "|---|---|---|---|");
    for (const w of v.who) lines.push(`| ${cell(w.what)} | ${cell(w.by)} | ${cell(w.at)} | ${cell(w.on)} |`);
  }
  return lines.join("\n") + "\n";
}

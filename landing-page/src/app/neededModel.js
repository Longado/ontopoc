// Questions we need (needed_questions.py): the words of the list, its expectations and what a run found. The service decides each outcome; this only says it.
import { formatDate, t } from "./i18n/index.js";
import { formatNumber } from "./explorerModel.js";

export const OUTCOMES = ["passes", "differs", "needs_look", "refused", "no_answer", "no_expectation", "not_run"];

/** A number as exactly as the service compares it, with thousands marked: 1234.5678 -> "1,234.5678", 0.30000000000000004 as it is. */
export function exactNumber(value) {
  const n = Number(value);
  if (value === null || value === undefined || !Number.isFinite(n)) return formatNumber(value);
  const text = String(n);
  if (/e/i.test(text)) return text;
  const [whole, fraction] = text.replace("-", "").split(".");
  return `${n < 0 ? "-" : ""}${whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${fraction ? `.${fraction}` : ""}`;
}

const calls = (count) => t("needed.run.calls", { count });

/** The line before a run: how many questions, how many times each, at most how many model calls, and where that sits with the runs' own budget line. */
export function planText(listing, repeats) {
  const count = listing.questions.length;
  const { calls: limit, hours, left } = listing.budget;
  return t("needed.run.plan", { questions: t("needed.run.questions", { count }), times: t("needed.times", { count: repeats }), calls: calls(count * repeats), limit, hours, left });
}

/** Whether a run of this many asks may start now: the service's own reason first, then whether the runs' budget has room for every call it may make. */
export function runAllowed(listing, repeats) {
  if (!listing.can_run?.ok) return { ok: false, why: listing.can_run?.why ?? "" };
  const most = listing.questions.length * repeats;
  if (most > listing.budget.left) return { ok: false, why: t("needed.run.tooMany", { calls: calls(most), left: listing.budget.left, hours: listing.budget.hours }) };
  return { ok: true, why: null };
}

/** What a question should give: a number, a refusal, or nothing written yet. */
export function expectText(expect) {
  if (expect == null) return t("needed.expect.none");
  if (expect.kind === "refused") return expect.blocker ? t("needed.expect.refusedBy", { name: expect.blocker }) : t("needed.expect.refused");
  return t("needed.expect.number", { value: exactNumber(expect.value) });
}

const movedOne = (m) => (m.from == null ? t("needed.moved.new", { name: m.name }) : m.to == null ? t("needed.moved.gone", { name: m.name }) : t("needed.moved.version", { name: m.name, from: m.from, to: m.to }));
const movedText = (moved) => (moved ?? []).map(movedOne).join(t("needed.sep"));

/** Where the expectation stands: waiting for one, proposed by whom, confirmed by whom and when, or what moved since it was confirmed. */
export function stateText(item) {
  if (item.state === "proposed") return t("needed.state.proposed", { name: item.written_by });
  if (item.state === "confirmed") return t("needed.state.confirmed", { name: item.confirmed_by, at: formatDate(item.confirmed_at) }) + (item.self_confirmed ? t("needed.state.self") : "");
  if (item.state === "needs_look") return t("needed.state.needsLook", { moved: movedText(item.look) });
  return t("needed.state.none");
}

/** Whether this person may confirm the expectation now: one is written and not confirmed, and while two-person confirmation is on it is not their own. */
export const canConfirm = (item, twoPerson) => (item.state === "proposed" || item.state === "needs_look") && !(twoPerson && item.mine);

/** Why the Confirm button is not offered to the person who wrote it, or "". */
export const confirmHint = (item, twoPerson) => ((item.state === "proposed" || item.state === "needs_look") && twoPerson && item.mine ? t("needed.confirmHint") : "");

/** An outcome in a word. */
export const outcomeWord = (outcome) => t(`needed.outcome.${outcome}`);

const answerWord = (d) => (d.number != null ? exactNumber(d.number) : d.status === "answered" || d.status === "no_data" ? t("needed.distinct.noNumber") : t("needed.distinct.refused"));

/** Each distinct answer the asks gave and how often: "160 (2 times), 1,234,567.5 (once)". */
export const distinctText = (distinct) => (distinct ?? []).map((d) => t("needed.distinct.item", { answer: answerWord(d), times: t("needed.times", { count: d.times }) })).join(t("needed.sep"));

/** A definition that blocks a question, as a person reads it: what it is, where it stands, who can confirm it. */
export function blockingText(b) {
  if (b.kind === "unmet") return t("needed.blocking.unmet", { name: b.name, why: b.why ?? "" });
  const line = t("needed.blocking.line", { kind: t(`needed.kind.${b.kind}`), name: b.name, state: t(`needed.blockState.${b.state}`) });
  return b.who_can_confirm?.length ? line + t("needed.blocking.who", { names: b.who_can_confirm.join(t("needed.sep")) }) : line;
}

const blockingLines = (blocking) => blocking.map(blockingText).join(t("needed.lineSep"));
const rightText = (r) => t(r.expected?.kind === "refused" ? "needed.right.refused" : "needed.right.number", { right: r.right, asked: r.asked });
const gotText = (r) => t("needed.result.got", { expect: expectText(r.expected), answers: distinctText(r.distinct) });

function answerLines(answer, blocking, distinct) {
  if (distinct?.length > 1) return [t("needed.result.several", { answers: distinctText(distinct) })];   // two answers to one question: neither is offered to adopt
  if (answer?.number != null) return [t("needed.result.answer", { number: exactNumber(answer.number) }), ...(answer.query_text ? [answer.query_text] : [])];
  if (answer?.status === "answered" || answer?.status === "no_data") return [t("needed.result.answerNoNumber")];
  if (blocking?.length) return [t("needed.result.answerBlocked", { lines: blockingLines(blocking) })];
  return [t("needed.result.answerRefused", { reason: answer?.reason ?? "" })];
}

/** What a question came back as in the last run, in lines a person reads under the outcome. */
export function resultLines(result) {
  let lines;
  if (result.outcome === "passes") lines = [rightText(result)];
  else if (result.outcome === "differs") lines = [rightText(result), gotText(result)];
  else if (result.outcome === "refused") {
    lines = [result.blocking?.length ? t("needed.result.blocked", { lines: blockingLines(result.blocking) }) : t("needed.result.refused", { reason: result.reason ?? "" })];
    if (result.expected?.kind === "refused" && result.expected.blocker) lines.push(t("needed.result.otherBlocker", { name: result.expected.blocker }));
  } else if (result.outcome === "no_answer") lines = [t("needed.result.noAnswer", { reason: result.reason ?? "" })];
  else if (result.outcome === "no_expectation") lines = answerLines(result.answer, result.blocking, result.distinct);
  else if (result.outcome === "needs_look") lines = [gotText(result), t("needed.result.moved", { moved: movedText(result.moved) })];
  else lines = [t("needed.result.notRun")];
  const other = result.reads_otherwise;
  if (other && (other.now?.length || other.not_now?.length)) {
    const parts = [other.now?.length ? t("needed.reads.now", { names: other.now.join(t("needed.sep")) }) : "", other.not_now?.length ? t("needed.reads.notNow", { names: other.not_now.join(t("needed.sep")) }) : ""];
    lines = [...lines, t("needed.result.readsOtherwise", { parts: parts.filter(Boolean).join(t("needed.lineSep")) })];
  }
  return result.reworded ? [...lines, t("needed.result.reworded")] : lines;
}

/** The number a person can adopt as the expectation: every ask gave this one number and there was nothing to hold it against. */
export function adoptable(result) {
  if (result?.outcome !== "no_expectation" || result.distinct?.length !== 1) return null;
  return result.distinct[0].number ?? null;
}

/** The form's choice as the service reads it: null (not known yet), a number as typed, or a refusal. */
export function expectPayload({ kind, value, blocker }) {
  if (kind === "number") return { kind: "number", value };
  if (kind !== "refused") return null;
  const named = (blocker ?? "").trim();
  return named ? { kind: "refused", blocker: named } : { kind: "refused" };
}

/** While a run goes: whose, and how many of its model calls it has made. */
export const runningText = (running) => t("needed.run.going", { by: running.by, calls: running.calls, planned: running.planned });

/** The last run in one line: who, when, how many model calls, which model. */
export function lastRunText(run) {
  const head = t("needed.last.line", { by: run.by, at: formatDate(run.at), calls: calls(run.calls) });
  return run.model ? `${head} · ${t("needed.last.model", { model: run.model })}` : head;
}

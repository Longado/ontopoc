// The Ask chat's client-side conversation, as plain functions so they can be tested without a browser.
// A turn is one question and its answer: {id, kind: "ask" | "query" | "saved", text, status: "thinking" | "done" | "error", record, error}.
// Nothing here is kept on the server: the thread is this session's questions in order; a past question opens as a thread of one.
import { exampleQuestions } from "./homeModel.js";

const pad = (n) => String(n).padStart(2, "0");
const localDay = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** The saved questions grouped by the day they were asked (local time), newest day first, each group newest first:
 * [{key: "today" | "yesterday" | "YYYY-MM-DD" | "undated", when, items}]. The component words the key; `when` is an ISO time of the group for formatting. */
export function groupByDay(history, now = new Date()) {
  const today = localDay(now);
  const yesterday = localDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1));
  const rows = (history ?? []).map((h) => {
    const d = new Date(h.asked_at);
    const ok = !Number.isNaN(d.getTime());
    return { h, time: ok ? d.getTime() : null, day: ok ? localDay(d) : "undated" };
  });
  rows.sort((a, b) => (b.time ?? -Infinity) - (a.time ?? -Infinity));
  const groups = [];
  const seen = new Set();
  for (const { h, day } of rows) {
    const same = `${h.mode ?? "ask"}|${String(h.question ?? "").replace(/\s+/g, " ").trim().toLowerCase()}`;
    if (String(h.question ?? "").trim() && seen.has(same)) continue;   // the same question asked again shows once, at its newest asking
    seen.add(same);
    let g = groups[groups.length - 1];
    if (!g || g.date !== day) {
      g = { date: day, key: day === today ? "today" : day === yesterday ? "yesterday" : day, when: h.asked_at, items: [] };
      groups.push(g);
    }
    g.items.push(h);
  }
  return groups.map(({ date, ...g }) => g);
}

let counter = Date.now();   // a thread kept in the tab comes back with its ids: new ones must not repeat them
/** A turn that is waiting for its answer. */
export const newTurn = (kind, text) => ({ id: `t${++counter}`, kind, text, status: "thinking", record: null, error: "" });
/** A saved answer opened from the history or from #/qa/<id>: a thread of one, loaded when it renders. */
export const savedTurn = (savedId) => ({ id: `s${savedId}`, kind: "saved", savedId, text: "", status: "thinking", record: null, error: "" });
/** The thread with one turn changed. */
export const settle = (turns, id, patch) => turns.map((t) => (t.id === id ? { ...t, ...patch } : t));
/** True while any turn waits for its answer (one question at a time, as before). */
export const isThinking = (turns) => turns.some((t) => t.status === "thinking");

/** Whether a key press in the composer sends: Enter sends and Shift+Enter breaks the line, unless an input method is composing;
 * the query box takes many lines, so there Enter breaks the line and Ctrl or Command + Enter runs. */
export function sendsOn(e, mode = "ask") {
  if (e.key !== "Enter" || e.isComposing || e.keyCode === 229) return false;
  return mode === "query" ? Boolean(e.ctrlKey || e.metaKey) : !e.shiftKey;
}

/** A few questions to try for what is in scope: how many of each confirmed type, then "A by B" for each relation between them (the home page's examples). */
export function suggestions(scope, relations = [], max = 3) {
  const types = (scope?.types ?? []).map((x) => ({ ...x, state: "confirmed" }));
  return exampleQuestions(types, relations, max);
}

/** The line over the thread: the first question, cut to fit, or empty for a new chat. */
export function threadTitle(turns, max = 60) {
  const first = turns.find((t) => t.text || t.record?.question);
  const text = String(first?.text || first?.record?.question || "").replace(/\s+/g, " ").trim();
  return text.length > max ? `${text.slice(0, max - 1)}…` : text;
}

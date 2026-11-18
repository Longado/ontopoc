import { t } from "./i18n/index.js";

// One vocabulary of states for the whole product: 草稿 / 待确认 / 已确认 / 需再看 / 已退回 / 失败, in grey / blue / green / orange / red / red.
// The pages keep the states their services send (proposed, checked, needs_look, approved ...); this table says which of the five each one is.

export const STATUS_KEYS = ["draft", "pending", "confirmed", "look", "rejected", "failed"];

const TONES = { draft: "grey", pending: "blue", confirmed: "green", look: "orange", rejected: "red", failed: "red" };   // rejected: a definition sent back with a reason; failed: a run or a request that failed
const word = (key) => ({ label: t(`status.${key}`), tone: TONES[key] });

// what each state the app already uses means; `hint` keeps the page's own old word for a tooltip
const MAP = {
  draft: ["draft"], model_draft: ["draft"], withdrawn: ["draft"], cancelled: ["draft"],
  proposed: ["pending"], checked: ["pending"], pending: ["pending"],
  confirmed: ["confirmed"], approved: ["confirmed"], success: ["confirmed"], done: ["confirmed"],
  look: ["look"], needs_look: ["look"], stale: ["look"],
  rejected: ["rejected"], failed: ["failed"], error: ["failed"], interrupted: ["failed", "interrupted"],
};

/** A state as {key, label, tone, hint}. `opts.modelDraft`: a model's draft is a draft, whatever its state says. Running work is {key:"running", label:"进行中", tone:"blue"};
 * a state not in the table is a grey chip with its own text. */
export function statusOf(raw, opts = {}) {
  if (opts.modelDraft) return { key: "draft", ...word("draft"), hint: "" };
  if (raw === "running") return { key: "running", label: t("status.running"), tone: "blue", hint: "" };
  const hit = MAP[raw];
  if (!hit) return raw ? { key: "draft", label: String(raw), tone: "grey", hint: "" } : { key: "draft", ...word("draft"), hint: "" };
  return { key: hit[0], ...word(hit[0]), hint: hit[1] ? t(`status.${hit[1]}`) : "" };
}

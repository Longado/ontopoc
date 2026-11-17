// One vocabulary of states for the whole product: 草稿 / 待确认 / 已确认 / 需再看 / 已退回 / 失败, in grey / blue / green / orange / red / red.
// The pages keep the states their services send (proposed, checked, needs_look, approved ...); this table says which of the five each one is.

export const STATUS_KEYS = ["draft", "pending", "confirmed", "look", "rejected", "failed"];

const WORDS = {
  draft: { label: "草稿", tone: "grey" },
  pending: { label: "待确认", tone: "blue" },
  confirmed: { label: "已确认", tone: "green" },
  look: { label: "需再看", tone: "orange" },
  rejected: { label: "已退回", tone: "red" },   // a definition sent back with a reason
  failed: { label: "失败", tone: "red" },   // a run or a request that failed
};

// what each state the app already uses means; `hint` keeps the page's own old word for a tooltip
const MAP = {
  draft: ["draft"], model_draft: ["draft"], withdrawn: ["draft"], cancelled: ["draft"],
  proposed: ["pending"], checked: ["pending"], pending: ["pending"],
  confirmed: ["confirmed"], approved: ["confirmed"], success: ["confirmed"], done: ["confirmed"],
  look: ["look"], needs_look: ["look"], stale: ["look"],
  rejected: ["rejected"], failed: ["failed"], error: ["failed"], interrupted: ["failed", "中断"],
};

/** A state as {key, label, tone, hint}. `opts.modelDraft`: a model's draft is a draft, whatever its state says. Running work is {key:"running", label:"进行中", tone:"blue"};
 * a state not in the table is a grey chip with its own text. */
export function statusOf(raw, opts = {}) {
  if (opts.modelDraft) return { key: "draft", ...WORDS.draft, hint: "" };
  if (raw === "running") return { key: "running", label: "进行中", tone: "blue", hint: "" };
  const hit = MAP[raw];
  if (!hit) return raw ? { key: "draft", label: String(raw), tone: "grey", hint: "" } : { key: "draft", ...WORDS.draft, hint: "" };
  return { key: hit[0], ...WORDS[hit[0]], hint: hit[1] ?? "" };
}

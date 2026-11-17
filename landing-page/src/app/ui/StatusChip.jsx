import React from "react";
import { statusOf } from "../statusModel.js";

/** The one state chip. Props: `state` (any state word the services send: proposed, checked, confirmed, needs_look, rejected, pending, approved, draft, running, failed ... or one of
 * draft/pending/confirmed/look/failed), `modelDraft` (a model's draft is shown as Draft), `label` (replaces the word, e.g. "Needs review: data changed"), `title` (tooltip). */
export function StatusChip({ state, modelDraft = false, label, title }) {
  const s = statusOf(state, { modelDraft });
  return <span className={`chip chip-${s.tone}`} title={title ?? (s.hint || undefined)}><span className="chip-dot" aria-hidden="true" />{label ?? s.label}</span>;
}

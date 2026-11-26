// The words of a drafted action on the Q&A page (action_drafts.py), as plain functions of what the service sends, so they can be tested without a browser.
import { t } from "./i18n/index.js";

/** Whether a Q&A record is a draft of an action: the assistant drafted it, nobody has submitted it. */
export const isDraft = (record) => record?.status === "draft" && !!record.draft;

/** A draft as the card shows it: {title, rows: [{key, name, current, asked}], form, note, offerForm, reasonNote}. `submitted`: the person sent it from the card, so
 * the note that nothing is submitted is gone (null) and the form is not offered again. `reasonNote` says the assistant's reason was too long and is left for the person to write (null otherwise). `rows` put the object's current value (read by the service, never
 * sent to the model) beside the value asked for; `form` is what RunAction is opened with, prefilled. A create has no object yet (objectKey null: the key is
 * in its form); a delete asks for no value. */
export function draftView(record, { submitted = false } = {}) {
  const d = record.draft;
  const kind = d.action.kind;
  const rows = (d.beside ?? []).map((r) => ({ key: r.column, name: r.name, current: r.current ?? t("ask.actionDraft.none"), asked: r.asked ?? (kind === "delete" ? t("ask.actionDraft.removed") : "") }));
  return {
    title: t("ask.actionDraft.title", { action: d.action.name, object: d.object }),
    rows,
    form: { action: d.action, objectKey: kind === "create" ? null : d.key, objectText: d.object, values: d.values ?? {}, reason: d.reason ?? "" },
    note: submitted ? null : t("ask.actionDraft.note"),
    offerForm: !submitted,   // one submit per draft from the card
    reasonNote: d.reason_too_long ? t("ask.actionDraft.reasonTooLong") : null,
  };
}

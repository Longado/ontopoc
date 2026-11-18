import React from "react";
import { formatDateTime, useT } from "../i18n/index.js";
import { Icon } from "./Icon.jsx";

/** "Drafted by the assistant": shown on an object that was applied from the assistant's draft (the service stores who applied it and when). Nothing for any other object. */
export function DraftedChip({ item }) {
  const t = useT();
  const d = item?.drafted;
  if (!d) return null;
  return <span className="chip chip-assistant" title={t("ask.assistant.drafted.title", { by: d.by ?? "", when: formatDateTime(d.at) })}><Icon name="bot" size={11} />{t("ask.assistant.drafted")}</span>;
}

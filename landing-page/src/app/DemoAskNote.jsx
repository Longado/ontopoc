import React from "react";
import { useT } from "./i18n/index.js";
import { QUICK_START_URL } from "./demoModel.js";
import { hrefFor } from "./routeModel.js";

/** Shown to a guest of a public demo in place of the question box: questions are off, boards carry the answers. */
export function DemoAskNote() {
  const t = useT();
  return (
    <div className="as-notice demo-ask-note" role="status">
      <p>{t("auth.guest.askOff.text")} <a href={QUICK_START_URL} target="_blank" rel="noopener noreferrer">{t("auth.guest.askOff.quickstart")}</a></p>
      <a className="button secondary" href={hrefFor({ page: "boards" })}>{t("auth.guest.openBoards")}</a>
    </div>
  );
}

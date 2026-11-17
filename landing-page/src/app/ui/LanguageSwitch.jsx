import React from "react";
import { LOCALES, setLocale, t, useT } from "../i18n/index.js";
import { Icon } from "./Icon.jsx";

/** The English / 中文 switch. Props: `variant` "menu" (rows with a check mark, for the avatar menu) or "inline" (small text buttons, for the sign-in page), `onPick` (called after a choice).
 * Switching re-renders the app at once, with no reload. */
export function LanguageSwitch({ variant = "menu", onPick }) {
  const { locale } = useT();
  const pick = (code) => {
    setLocale(code);
    onPick?.(code);
  };
  if (variant === "inline") {
    return (
      <div className="lang-inline" role="group" aria-label={t("common.language")}>
        {LOCALES.map((code) => (
          <button key={code} type="button" className="plain" lang={code} aria-pressed={code === locale} onClick={() => pick(code)}>{t(`common.lang.${code}`)}</button>
        ))}
      </div>
    );
  }
  return (
    <div className="menu-lang" role="group" aria-label={t("common.language")}>
      <p className="menu-label">{t("common.language")}</p>
      {LOCALES.map((code) => (
        <button key={code} type="button" role="menuitemradio" aria-checked={code === locale} lang={code} className="menu-item" onClick={() => pick(code)}>
          <span className="menu-check">{code === locale && <Icon name="check" size={16} />}</span>{t(`common.lang.${code}`)}
        </button>
      ))}
    </div>
  );
}

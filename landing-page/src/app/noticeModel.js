// What a notice on the Messages page leads to (NoticesPage).
import { t } from "./i18n/index.js";
import { itemHref } from "./relationModel.js";

/** The link a notice carries: to the definition that went back to needs another look, worded "confirm" when this person may confirm it now (the service says) and
 * "open" otherwise; null for a notice from an action, which quotes its row and links nowhere. */
export function noticeLink(notice) {
  const d = notice?.definition;
  if (!d) return null;
  return { href: itemHref(d), label: d.can_confirm ? t("notices.confirm") : t("notices.open") };
}

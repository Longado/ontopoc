// The object page's related objects as plain functions of what the service sends.
import { t } from "./i18n/index.js";
import { joinList } from "./typeModel.js";

/** Locate the visible name column when it contains a value for this row. */
export function objectNameIndex(columns, row) {
  const i = columns.findIndex((c) => !c.key && !c.derived && /(\u540d\u79f0|\u540d|name)$/i.test(c.name));
  const value = i < 0 ? null : row[i];
  return value == null || !String(value).trim() ? -1 : i;
}

export function objectName(columns, row) {
  const i = objectNameIndex(columns, row);
  return i === -1 ? "" : String(row[i]).trim();
}

/** Only a complete standalone web address becomes a link; fragments locate a page or recording. */
export function sourceHref(value) {
  if (typeof value !== "string") return null;
  const href = value.trim();
  if (!/^https?:\/\/[^\s\\]+$/iu.test(href)) return null;
  try {
    const url = new URL(href);
    return url.hostname && !url.username && !url.password ? href : null;
  } catch {
    return null;
  }
}

/** One related object's label: its key, and its name beside it when its type has a name column ("KH022 + Suzhou · Suzhou Appliances 22"). */
export const objectLabel = (o) => (o.name ? `${o.text} · ${o.name}` : o.text);

/** A relation's card on the object page: the objects with their labels, and "and 12 more" when there are more than are listed. Whether the relation is confirmed is said once for the page. */
export function relatedCard(r) {
  return {
    objects: r.objects.map((o) => ({ n: o.n, label: objectLabel(o) })),
    more: r.count > r.objects.length ? t("objects.model.more", { count: r.count }) : "",
  };
}

/** The one line at the top of the page about relations nobody has confirmed yet; "" when all are. */
export function unconfirmedNote(related) {
  const open = related.filter((r) => !r.confirmed);
  return open.length ? t("objects.model.unconfirmed", { count: open.length, names: joinList(open.map((r) => r.name)) }) : "";
}

// The object page's related objects as plain functions of what the service sends.

/** The value of the column that names the object (客户名称, name): a column that is not a key and not derived, called ...名称, ...名 or ...name. "" when none, or when it is empty. */
export function objectName(columns, row) {
  const i = columns.findIndex((c) => !c.key && !c.derived && /(名称|名|name)$/i.test(c.name));
  const value = i < 0 ? null : row[i];
  return value == null ? "" : String(value).trim();
}

/** One related object's label: its key, and its name beside it when its type has a name column ("KH022 + 苏州 · 苏州家电客户22"). */
export const objectLabel = (o) => (o.name ? `${o.text} · ${o.name}` : o.text);

/** A relation's card on the object page: the objects with their labels, and "等 12 个" when there are more than are listed. Whether the relation is confirmed is said once for the page. */
export function relatedCard(r) {
  return {
    objects: r.objects.map((o) => ({ n: o.n, label: objectLabel(o) })),
    more: r.count > r.objects.length ? `等 ${r.count} 个` : "",
  };
}

/** The one line at the top of the page about relations nobody has confirmed yet; "" when all are. */
export function unconfirmedNote(related) {
  const open = related.filter((r) => !r.confirmed);
  return open.length ? `有 ${open.length} 个关系还没确认：${open.map((r) => r.name).join("、")}。关联到的对象可能会变。` : "";
}

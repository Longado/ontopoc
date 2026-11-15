// The 权限 page's reasoning as plain functions: who sees a type now, who a row-rule list would cut off, who a change to the visibility list takes the type from.

/** The people who see the type now (the admin always does and is left out: nothing here can take it from them); a viewer needs it confirmed too. */
export const seers = (type, people) =>
  people.filter((p) => p.role !== "admin" && (type.everyone || type.user_ids.includes(p.id)) && (p.role !== "viewer" || type.state === "confirmed"));

/** Of the people who see the type, the ones no rule in the list names: with any rule at all, they see no row. */
export function cutOff(type, people, rules) {
  if (!rules.length) return [];
  const named = new Set(rules.flatMap((r) => r.user_ids));
  return seers(type, people).filter((p) => !named.has(p.id));
}

/** What goes in with the first rule of a type: an all-rows entry for the people who see it now and the new rule does not name, or null when it is not the first or nobody is left. */
export function prefilledRule(type, people, rule) {
  if (type.row_rules.length) return null;
  const ids = seers(type, people).filter((p) => !rule.user_ids.includes(p.id)).map((p) => p.id);
  return ids.length ? { column: "", value: "", user_ids: ids, prefilled: true } : null;
}

/** The people who see the type now and would not after it is set to `visibleTo` ("everyone" is [] with everyone true; here: a list of ids, or "everyone"). */
export function loseAccess(type, visibleTo, people) {
  if (visibleTo === "everyone") return [];
  return seers(type, people).filter((p) => !visibleTo.includes(p.id));
}

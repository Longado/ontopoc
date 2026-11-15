// The 权限 page's reasoning as plain functions: who sees a type now, who a row-rule list would cut off, who a change to the visibility list takes the type from.

/** The people who see the type now (the admin always does and is left out: nothing here can take it from them); a viewer needs it confirmed too. */
export const seers = (type, people) =>
  people.filter((p) => p.role !== "admin" && (type.everyone || type.user_ids.includes(p.id)) && (p.role !== "viewer" || type.state === "confirmed"));

/** Whether a rule lets this person see some rows: it names them, or it compares with an attribute they have. */
export const covers = (rule, person) => (rule.user_attr ? !!person.attrs?.[rule.user_attr] : rule.user_ids.includes(person.id));

/** Of the people who see the type, the ones no rule in the list covers: with any rule at all, they see no row. */
export function cutOff(type, people, rules) {
  if (!rules.length) return [];
  return seers(type, people).filter((p) => !rules.some((r) => covers(r, p)));
}

/** A rule in words: "Ann、Bob 看 区域 = 华东 的行", "每个人看 区域 = 自己的部门 的行", or "Ann 看全部行". */
export function ruleText(rule, columnName, names) {
  if (rule.user_attr) return `每个人看 ${columnName} = 自己的${rule.user_attr} 的行`;
  return `${names} 看${rule.column ? ` ${columnName} = ${rule.value} 的行` : "全部行"}`;
}

/** The attribute names the people have, for the rule form to offer. */
export const attrNames = (people) => [...new Set(people.flatMap((p) => Object.keys(p.attrs ?? {})))].sort();

/** What goes in with the first rule of a type: an all-rows entry for the people who see it now and the new rule does not name, or null when it is not the first or nobody is left. */
export function prefilledRule(type, people, rule) {
  if (type.row_rules.length) return null;
  const ids = seers(type, people).filter((p) => !covers(rule, p)).map((p) => p.id);
  return ids.length ? { column: "", value: "", user_ids: ids, prefilled: true } : null;
}

/** The people who see the type now and would not after it is set to `visibleTo` ("everyone" is [] with everyone true; here: a list of ids, or "everyone"). */
export function loseAccess(type, visibleTo, people) {
  if (visibleTo === "everyone") return [];
  return seers(type, people).filter((p) => !visibleTo.includes(p.id));
}

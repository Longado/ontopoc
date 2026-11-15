/** 组织架构模式的运行，摆成一份报告会画的样子：组织树、协作交接、角色表。所有内容来自建模结果，页面不另算。 */

const TREE_TYPES = ["unit", "role", "person"];
const FLOW_KINDS = ["hands_to", "works_with"];

export const isOrg = (run) => run?.mode === "org";

const entities = (run) => run.ontology.object_types || [];
const facts = (run) => run.ontology.relations || [];
const named = (run) => Object.fromEntries(entities(run).map((t) => [t.key, t]));

/** 智能问答式的二级导航：每个位置带它有多少条；空的位置不列（时期、未说明常常没有）。 */
export function orgPlaces(run) {
  const periods = run.evaluation.periods || { periods: [], undated: [] };
  const counts = [
    ["tree", "组织树", entities(run).filter((t) => TREE_TYPES.includes(t.org_type)).length],
    ["flow", "协作交接", facts(run).filter((r) => FLOW_KINDS.includes(r.kind)).length],
    ["roles", "角色", entities(run).filter((t) => t.org_type === "role").length],
    ["periods", "时期", periods.periods.length + periods.undated.length],
    ["open", "未说明", (run.ontology.open || []).length],
  ];
  return counts.filter(([key, , n]) => n > 0 || key === "tree" || key === "flow" || key === "roles").map(([k, t, n]) => [k, t, String(n)]);
}

/** 隶属在上、担任在下：岗位挂在所属组织单元下，人挂在他担任的岗位下，汇报关系同样往上挂。 */
export function orgTree(run) {
  const nodes = Object.fromEntries(entities(run).filter((t) => TREE_TYPES.includes(t.org_type))
    .map((t) => [t.key, { key: t.key, label: t.label, type: t.org_type, note: t.definition || "", children: [] }]));
  const parent = {};
  for (const r of facts(run)) {
    const [child, above] = r.kind === "part_of" || r.kind === "holds" || r.kind === "reports_to" ? [r.from, r.to] : [];
    if (nodes[child] && nodes[above] && !parent[child] && child !== above) parent[child] = above;
  }
  const cycles = (key) => {   // a chain that loops back would hide its own nodes
    const seen = new Set();
    for (let at = key; at; at = parent[at]) {
      if (seen.has(at)) return true;
      seen.add(at);
    }
    return false;
  };
  for (const [child, above] of Object.entries(parent)) {
    if (cycles(child)) continue;
    nodes[above].children.push(nodes[child]);
  }
  const roots = Object.values(nodes).filter((n) => !parent[n.key] || cycles(n.key));
  return { roots: roots.filter((n) => n.children.length), loose: roots.filter((n) => !n.children.length).map((n) => n.label) };
}

/** 每条交接一行：谁交给谁、交了什么、什么时候；协作画成双向。 */
export function handoffLines(run) {
  const by = named(run);
  return facts(run).filter((r) => FLOW_KINDS.includes(r.kind)).map((r) => ({
    key: r.key, from: by[r.from]?.label || r.from, to: by[r.to]?.label || r.to,
    what: r.what || null, when: r.when || null, both: r.kind === "works_with",
  }));
}

/** 报告里那张角色表：角色、职责、在哪个组织单元、谁担任、和谁交接。 */
export function roleRows(run) {
  const by = named(run);
  const label = (key) => by[key]?.label || key;
  return entities(run).filter((t) => t.org_type === "role").map((t) => {
    const partners = [];
    for (const r of facts(run)) {
      if (!FLOW_KINDS.includes(r.kind)) continue;
      const other = r.from === t.key ? r.to : r.to === t.key ? r.from : null;
      if (other && !partners.includes(label(other))) partners.push(label(other));
    }
    return {
      key: t.key, label: t.label, note: t.definition || "",
      unit: facts(run).filter((r) => r.kind === "part_of" && r.from === t.key).map((r) => label(r.to))[0] || "",
      duties: facts(run).filter((r) => r.kind === "responsible_for" && r.from === t.key).map((r) => label(r.to)),
      people: facts(run).filter((r) => r.kind === "holds" && r.to === t.key).map((r) => label(r.from)),
      partners,
    };
  });
}

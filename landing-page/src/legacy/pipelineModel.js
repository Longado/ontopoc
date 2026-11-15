// A pipeline built on the 数据接入 page: two inputs (a stored table or a view) joined on a key, with the rows of every step counted.
const NUMBER = new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 2 });
export const HOW_CHOICES = [["left", "保留左边的全部行"], ["inner", "只留两边对得上的行"]];

/** The tables of a run that were stored in the workspace, with their column names. */
export const pipelineTables = (tables) => tables.filter((t) => t.checks && !t.checks.error && t.fields?.length)
  .map((t) => ({ name: t.name, rows: t.rows, columns: t.fields.map((f) => f.path) }));

/** The tables of a run whose draft did not pass the checks have no field list on the page; the workspace's own list of what it stored says the columns. */
export const storedPipelineTables = (viewTables = []) => viewTables.map((t) => ({ name: t.name, columns: t.columns.map((c) => c.name) }));

/** What a join can read: each stored table and each view that can be read, told apart by kind (a view may carry a table's name). */
export const pipelineSources = (tables, views = []) => [
  ...tables.map((t) => ({ id: `表:${t.name}`, kind: "表", name: t.name, columns: t.columns })),
  ...views.filter((v) => v.state === "confirmed").map((v) => ({ id: `视图:${v.name}`, kind: "视图", name: v.name, columns: v.columns.map((c) => c.name) })),
];

const find = (sources, id) => sources.find((s) => s.id === id);
export const sourceLabel = (sources, id) => { const s = find(sources, id); return s ? `${s.kind} ${s.name}` : ""; };

/** A starting form: the first two inputs that have a column of the same name, joined on it; else the first two. */
export function startForm(sources) {
  for (const left of sources) for (const right of sources) {
    const shared = left !== right && left.columns.find((c) => right.columns.includes(c));
    if (shared) return { left: left.id, right: right.id, leftKey: shared, rightKey: shared, how: "left" };
  }
  const [a, b] = sources;
  return { left: a?.id || "", right: b?.id || "", leftKey: "", rightKey: "", how: "left" };
}

/** The form after one choice: a key column that the newly chosen input does not have is dropped. */
export function setChoice(form, sources, part) {
  const next = { ...form, ...part };
  const has = (id, column) => find(sources, id)?.columns.includes(column);
  return { ...next, leftKey: has(next.left, next.leftKey) ? next.leftKey : "", rightKey: has(next.right, next.rightKey) ? next.rightKey : "" };
}

export const formProblem = (form) => (!form.left || !form.right ? "选两个输入" : form.left === form.right ? "左右要是两个不同的输入" : !form.leftKey || !form.rightKey ? "两边各选一列来对" : "");

const input = (id, source) => (source?.kind === "视图" ? { id, type: "input", view: source.name } : { id, type: "input", dataset: source?.name });

/** The pipeline the form says: an input for each side, a join on the key, an output. A pipeline is plain data. */
export const pipelineOf = (form, sources) => ({ steps: [
  input("left", find(sources, form.left)),
  input("right", find(sources, form.right)),
  { id: "joined", type: "join", left: "left", right: "right", how: form.how, on: [{ left: form.leftKey, right: form.rightKey }] },
  { id: "out", type: "output", from: "joined", name: `${find(sources, form.left)?.name}带${find(sources, form.right)?.name}` }] });

const n = (v) => NUMBER.format(v);

/** One line per step: its rows in and out. */
export function nodeLines(result, form, sources) {
  return result.nodes.map((node) => {
    if (node.type === "input") return { id: node.id, text: `${sourceLabel(sources, node.id === "left" ? form.left : form.right)}：${n(node.rows_out)} 行` };
    if (node.type === "join") {
      const kept = form.how === "left" ? `保留${sourceLabel(sources, form.left)}的全部行` : "只留对得上的行";
      return { id: node.id, text: `连接（${kept}）：${n(node.rows_in[0])} 行 + ${n(node.rows_in[1])} 行 → ${n(node.rows_out)} 行`, flagged: Boolean(node.join.fan_out || node.join.right_fan_out) };
    }
    return { id: node.id, text: `输出：${n(node.rows_out)} 行，只在这里看，没有写进任何表` };
  });
}

const exampleKeys = (fan, left, right, leftRows, rightRows) => fan.examples.map((e) => `${Object.values(e.key).join("、")}（${left}里 ${e[leftRows]} 行，${right}里 ${e[rightRows]} 行）`).join("；");

/** What a join says beyond its row counts: rows made beyond the left input and the sums counted twice, the same for the right
 *  input's numbers when the left repeats a key, keys that would match if read as numbers or trimmed, and empty keys. */
export function fanOutLines(node, form, sources) {
  const { fan_out: fan, right_fan_out: back, extra_rows: extra, left_rows: leftRows, matched_left: matched, near_matches: near = [], left_blank: leftBlank = 0, right_blank: rightBlank = 0 } = node.join;
  const [left, right] = [sourceLabel(sources, form.left), sourceLabel(sources, form.right)];
  const lines = [];
  if (fan) {
    const made = form.how === "left" ? `${n(node.rows_out)} 行比${left}自己的 ${n(leftRows)} 行多了 ${n(extra)} 行`
      : `对得上的 ${n(matched)} 行${left}变成了 ${n(node.rows_out)} 行，多了 ${n(extra)} 行`;
    const keys = exampleKeys(fan, left, right, "left_rows", "right_rows");
    lines.push(`${made}：「${fan.columns.join("、")}」在${right}里有 ${n(fan.repeated_keys)} 个值重复，${left}的一行连上了好几行。`,
      ...(keys ? [`例如 ${keys}${fan.repeated_keys > fan.examples.length ? "等" : ""}`] : []),
      ...(fan.double_counted.length ? [`${left}的这些数加起来会重复计算：${fan.double_counted.map((c) => `${c.column} ${n(c.without)} → ${n(c.with)}`).join("；")}`] : []));
  }
  if (back) {
    const keys = exampleKeys(back, left, right, "left_rows", "right_rows");
    lines.push(`${left}在「${back.columns.join("、")}」上有 ${n(back.repeated_keys)} 个值重复，${right}的一行被连了好几次：${right}的这些数加起来会重复计算：${back.double_counted.map((c) => `${c.column} ${n(c.without)} → ${n(c.with)}`).join("；")}`,
      ...(keys ? [`例如 ${keys}${back.repeated_keys > back.examples.length ? "等" : ""}`] : []));
  }
  for (const m of near) lines.push(`${left}的「${m.left}」有 ${n(m.count)} 个值，去掉前后空格或按数字读就能对上${right}的「${m.right}」，但这里按原文对，没对上（例如 ${m.examples.map((e) => `“${e}”`).join("、")}）`);
  if (leftBlank) lines.push(`${left}有 ${n(leftBlank)} 行的对接列是空的，空值不参与对接`);
  if (rightBlank) lines.push(`${right}有 ${n(rightBlank)} 行的对接列是空的，空值不参与对接`);
  return lines;
}

/** Always said beside the form: how keys are compared, and the most rows a join may make. */
export const joinRules = (rowCap) => `对列时按原文逐字比：前后空格、1 和 1.0 都算不同；空值不参与对接。一次连接最多产生 ${NUMBER.format(rowCap)} 行，超过就不运行。`;

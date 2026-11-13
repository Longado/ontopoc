// The app's addresses (#/datasets/订单/preview?v=2) and its left navigation, as plain data so both can be tested without a browser.
export const TABS = ["fields", "preview", "versions"];
export const TAB_LABEL = { fields: "字段", preview: "预览", versions: "版本" };

const decode = (part) => decodeURIComponent(part);

/** An address to the page it means: {page: "datasets" | "dataset" | "tasks" | "notfound", ...}. */
export function parseRoute(hash) {
  const raw = String(hash || "").replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  let parts;
  try {
    parts = path.split("/").filter(Boolean).map(decode);
  } catch {
    return { page: "notfound" };   // a broken %-escape in the name
  }
  if (!parts.length || (parts[0] === "datasets" && parts.length === 1)) return { page: "datasets" };
  if (parts[0] === "tasks" && parts.length === 1) return { page: "tasks" };
  if (parts.length === 1 && Object.hasOwn(PLANNED, parts[0])) return { page: "planned", key: parts[0] };
  if (parts[0] === "datasets" && parts.length <= 3) {
    const tab = parts[2] ?? "fields";
    if (!TABS.includes(tab)) return { page: "notfound" };
    const v = new URLSearchParams(query).get("v");
    return { page: "dataset", name: parts[1], tab, version: /^\d+$/.test(v ?? "") ? Number(v) : null };
  }
  return { page: "notfound" };
}

/** The address of a route; the inverse of parseRoute. */
export function hrefFor(route) {
  if (route.page === "tasks") return "#/tasks";
  if (route.page === "planned") return `#/${route.key}`;
  if (route.page === "dataset") {
    const base = `#/datasets/${encodeURIComponent(route.name)}/${route.tab ?? "fields"}`;
    return route.version ? `${base}?v=${route.version}` : base;
  }
  return "#/datasets";
}

// Pages not built yet: what each will do, in one line. The sidebar shows them in grey and they open a page saying exactly this.
export const PLANNED = {
  home: ["首页", "一个提问框和最近的任务，还没做"],
  pipelines: ["管道", "把数据集连接、清洗成新的数据集，每一步看得到行数，还没做"],
  sources: ["数据源", "连接 MySQL、PostgreSQL，把库里的表读成数据集，还没做"],
  types: ["对象类型", "从数据集建对象类型，还没做"],
  relations: ["关系", "定义对象类型之间的关系，看每条关系连上了多少行，还没做"],
  confirm: ["待确认", "逐条看模型的提议和数据检查，确认或退回，还没做"],
  qa: ["问答", "用已确认的定义回答业务问题，每个答案写明读了哪个版本，还没做"],
  agents: ["智能体", "给问答设定范围和说明，还没做"],
  boards: ["看板", "用已确认的指标做看板，还没做"],
  lineage: ["血缘", "从数据源到应用，看每一步用了什么，还没做"],
};

const BUILT = { tasks: "#/tasks", datasets: "#/datasets" };
const item = (key, label) => ({ key, label, href: BUILT[key] ?? `#/${key}`, built: key in BUILT });

export const NAV = [
  { items: [item("home", "首页"), item("tasks", "任务")] },
  { label: "数据", items: [item("datasets", "数据集"), item("pipelines", "管道"), item("sources", "数据源")] },
  { label: "本体", items: [item("types", "对象类型"), item("relations", "关系"), item("confirm", "待确认")] },
  { label: "应用", items: [item("qa", "问答"), item("agents", "智能体"), item("boards", "看板")] },
  { items: [item("lineage", "血缘")] },
];

/** Which navigation item a route lives under. */
export const navKeyOf = (route) => (route.page === "dataset" ? "datasets" : route.page === "planned" ? route.key : route.page);

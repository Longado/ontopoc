// The app's addresses (#/datasets/订单/preview?v=2&p=3, #/account, #/users) and its left navigation, as plain data so both can be tested without a browser.
export const TABS = ["fields", "preview", "versions"];
export const TAB_LABEL = { fields: "字段", preview: "预览", versions: "版本" };
export const TYPE_TABS = ["props", "views", "actions", "objects", "log"];
export const TYPE_TAB_LABEL = { props: "属性", views: "视图", actions: "行为", objects: "对象", log: "日志" };

const decode = (part) => decodeURIComponent(part);

/** An address to the page it means: {page: "qa" | "datasets" | "dataset" | "tasks" | "notfound", ...}. The empty address is the Q&A page, where the app opens. */
export function parseRoute(hash) {
  const raw = String(hash || "").replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  let parts;
  try {
    parts = path.split("/").filter(Boolean).map(decode);
  } catch {
    return { page: "notfound" };   // a broken %-escape in the name
  }
  if (!parts.length || (parts[0] === "qa" && parts.length === 1)) return { page: "qa", id: null };
  if (parts[0] === "qa" && parts.length === 2 && /^[1-9]\d*$/.test(parts[1])) return { page: "qa", id: Number(parts[1]) };   // a saved answer
  if (parts[0] === "datasets" && parts.length === 1) return { page: "datasets" };
  if (parts[0] === "tasks" && parts.length === 1) return { page: "tasks" };
  if ((parts[0] === "account" || parts[0] === "users") && parts.length === 1) return { page: parts[0] };
  if (parts.length === 1 && Object.hasOwn(PLANNED, parts[0])) return { page: "planned", key: parts[0] };
  if (parts[0] === "relations") {
    if (parts.length === 1) return { page: "relations" };
    if (parts.length === 2 && parts[1] === "new") return { page: "relationnew" };   // the service refuses a relation called new, so this address is never a relation
    if (parts.length === 3 && parts[2] === "edit") return { page: "relationedit", id: parts[1] };
    if (parts.length === 2) return { page: "relation", id: parts[1] };
    return { page: "notfound" };
  }
  if (parts.length === 1 && (parts[0] === "confirm" || parts[0] === "permissions")) return { page: parts[0] };
  if (parts[0] === "pipelines") {
    if (parts.length === 1) return { page: "pipelines" };
    if (parts.length === 2 && parts[1] === "new") return { page: "pipelinenew" };   // the service refuses a pipeline called new
    const view = parts[2] ?? "edit";
    if (parts.length === 2) return { page: "pipeline", name: parts[1], view };
    if (parts.length === 3 && ["runs", "history", "confirm"].includes(view)) return { page: "pipeline", name: parts[1], view };
    if (parts.length === 4 && view === "runs" && /^[1-9]\d*$/.test(parts[3])) return { page: "pipeline", name: parts[1], view: "run", run: Number(parts[3]) };
    return { page: "notfound" };
  }
  if (parts[0] === "types") {
    if (parts.length === 1) return { page: "types" };
    if (parts.length === 2 && parts[1] === "new") return { page: "typenew" };   // the service refuses a type called new, so this address is never a type
    if (parts.length === 3 && parts[2] === "edit") return { page: "typeedit", id: parts[1] };
    const tab = parts[2] ?? "props";
    const p = new URLSearchParams(query).get("p");
    if (parts.length <= 3 && TYPE_TABS.includes(tab)) return { page: "type", id: parts[1], tab, pageNo: /^[1-9]\d*$/.test(p ?? "") ? Number(p) : 1 };
    return { page: "notfound" };
  }
  if (parts[0] === "datasets" && parts.length <= 3) {
    const tab = parts[2] ?? "fields";
    if (!TABS.includes(tab)) return { page: "notfound" };
    const v = new URLSearchParams(query).get("v");
    const p = new URLSearchParams(query).get("p");
    return { page: "dataset", name: parts[1], tab, version: /^\d+$/.test(v ?? "") ? Number(v) : null, pageNo: /^[1-9]\d*$/.test(p ?? "") ? Number(p) : 1 };
  }
  return { page: "notfound" };
}

/** The address of a route; the inverse of parseRoute. */
export function hrefFor(route) {
  if (route.page === "qa") return route.id ? `#/qa/${route.id}` : "#/qa";
  if (route.page === "tasks" || route.page === "account" || route.page === "users") return `#/${route.page}`;
  if (route.page === "planned") return `#/${route.key}`;
  if (route.page === "types") return "#/types";
  if (route.page === "confirm" || route.page === "permissions" || route.page === "relations") return `#/${route.page}`;
  if (route.page === "pipelines") return "#/pipelines";
  if (route.page === "pipelinenew") return "#/pipelines/new";
  if (route.page === "pipeline") {
    const base = `#/pipelines/${encodeURIComponent(route.name)}`;
    return route.view === "run" ? `${base}/runs/${route.run}` : route.view && route.view !== "edit" ? `${base}/${route.view}` : base;
  }
  if (route.page === "relationnew") return "#/relations/new";
  if (route.page === "relation") return `#/relations/${encodeURIComponent(route.id)}`;
  if (route.page === "relationedit") return `#/relations/${encodeURIComponent(route.id)}/edit`;
  if (route.page === "typenew") return "#/types/new";
  if (route.page === "typeedit") return `#/types/${encodeURIComponent(route.id)}/edit`;
  if (route.page === "type") return `#/types/${encodeURIComponent(route.id)}/${route.tab ?? "props"}${route.pageNo > 1 ? `?p=${route.pageNo}` : ""}`;
  if (route.page === "dataset") {
    const base = `#/datasets/${encodeURIComponent(route.name)}/${route.tab ?? "fields"}`;
    const query = [route.version ? `v=${route.version}` : "", route.pageNo > 1 ? `p=${route.pageNo}` : ""].filter(Boolean).join("&");
    return query ? `${base}?${query}` : base;
  }
  return "#/datasets";
}

// Pages not built yet: what each will do, in one line. The sidebar shows them in grey and they open a page saying exactly this.
export const PLANNED = {
  sources: ["数据源", "连接 MySQL、PostgreSQL，把库里的表读成数据集，还没做"],
  agents: ["智能体", "给问答设定范围和说明，还没做"],
  boards: ["看板", "用已确认的指标做看板，还没做"],
  lineage: ["血缘", "从数据源到应用，看每一步用了什么，还没做"],
};

const BUILT = { qa: "#/qa", tasks: "#/tasks", datasets: "#/datasets", types: "#/types", relations: "#/relations", confirm: "#/confirm", users: "#/users", permissions: "#/permissions", pipelines: "#/pipelines" };
const BUILDERS = ["tasks", "confirm", "pipelines"];   // shown to builders and admins only: a viewer has nothing to confirm, the task list quotes keys and values and a pipeline's steps and previews quote rows (the service refuses them to a viewer)
const item = (key, label) => ({ key, label, href: BUILT[key] ?? `#/${key}`, built: key in BUILT, builders: BUILDERS.includes(key) });

export const NAV = [
  { items: [item("qa", "问答"), item("tasks", "任务")] },
  { label: "数据", items: [item("datasets", "数据集"), item("pipelines", "管道"), item("sources", "数据源")] },
  { label: "本体", items: [item("types", "对象类型"), item("relations", "关系"), item("confirm", "待确认")] },
  { label: "应用", items: [item("agents", "智能体"), item("boards", "看板")] },
  { items: [item("lineage", "血缘")] },
];

/** What only an admin sees. */
export const ADMIN_NAV = [{ label: "设置", items: [item("users", "用户"), item("permissions", "权限")] }];

/** Which navigation item a route lives under. */
export const navKeyOf = (route) =>
  route.page === "dataset" ? "datasets" : route.page === "planned" ? route.key : ["type", "typenew", "typeedit"].includes(route.page) ? "types" : ["pipeline", "pipelinenew"].includes(route.page) ? "pipelines" : route.page === "account" ? null : ["relation", "relationnew", "relationedit"].includes(route.page) ? "relations" : route.page;

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
  if (route.page === "dataset") {
    const base = `#/datasets/${encodeURIComponent(route.name)}/${route.tab ?? "fields"}`;
    return route.version ? `${base}?v=${route.version}` : base;
  }
  return "#/datasets";
}

// What is not built yet has no address: the sidebar shows it as plain grey text.
export const NAV = [
  { items: [{ key: "home", label: "首页" }, { key: "tasks", label: "任务", href: "#/tasks" }] },
  { label: "数据", items: [{ key: "datasets", label: "数据集", href: "#/datasets" }, { key: "pipelines", label: "管道" }, { key: "sources", label: "数据源" }] },
  { label: "本体", items: [{ key: "types", label: "对象类型" }, { key: "relations", label: "关系" }, { key: "confirm", label: "待确认" }] },
  { label: "应用", items: [{ key: "qa", label: "问答" }, { key: "agents", label: "智能体" }, { key: "boards", label: "看板" }] },
  { items: [{ key: "lineage", label: "血缘" }] },
];

/** Which navigation item a route lives under. */
export const navKeyOf = (route) => (route.page === "dataset" ? "datasets" : route.page);

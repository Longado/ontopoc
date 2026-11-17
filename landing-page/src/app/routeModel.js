import { canBuild, isAdmin } from "./authModel.js";
import { t } from "./i18n/index.js";

// The app's addresses (#/datasets/订单/preview?v=2&p=3, #/account, #/users) and its left navigation, as plain data so both can be tested without a browser.
export const TABS = ["fields", "preview", "versions"];
/** Tab names in the current language (getters: read at use time). */
const labels = (prefix, keys) => Object.defineProperties({}, Object.fromEntries(keys.map((k) => [k, { enumerable: true, get: () => t(`nav.${prefix}.${k}`) }])));
export const TAB_LABEL = labels("tab", TABS);
export const TYPE_TABS = ["props", "derived", "views", "actions", "objects", "log"];
export const TYPE_TAB_LABEL = labels("typeTab", TYPE_TABS);

/** `?dataset=name` on a "new" address: the dataset the page starts from (用它建管道, 用它建对象类型). */
const withDataset = (route, query) => {
  const dataset = new URLSearchParams(query).get("dataset");
  return dataset ? { ...route, dataset } : route;
};
const datasetQuery = (route) => (route.dataset ? `?dataset=${encodeURIComponent(route.dataset)}` : "");

const decode = (part) => decodeURIComponent(part);

/** An address to the page it means: {page: "home" | "qa" | "datasets" | "dataset" | "tasks" | "notfound", ...}. The empty address is the home page, where the app opens. */
export function parseRoute(hash) {
  const raw = String(hash || "").replace(/^#\/?/, "");
  const [path, query = ""] = raw.split("?");
  let parts;
  try {
    parts = path.split("/").filter(Boolean).map(decode);
  } catch {
    return { page: "notfound" };   // a broken %-escape in the name
  }
  if (!parts.length || (parts[0] === "home" && parts.length === 1)) return { page: "home" };
  if (parts[0] === "qa" && parts.length === 1) {
    const ask = (new URLSearchParams(query).get("ask") ?? "").trim();   // a question typed on the home page, asked as the Q&A page opens
    return ask ? { page: "qa", id: null, ask } : { page: "qa", id: null };
  }
  if (parts[0] === "qa" && parts.length === 2 && /^[1-9]\d*$/.test(parts[1])) return { page: "qa", id: Number(parts[1]) };   // a saved answer
  if (parts[0] === "datasets" && parts.length === 1) return { page: "datasets" };
  if (parts[0] === "tasks" && parts.length === 1) return { page: "tasks" };
  if (parts[0] === "notices" && parts.length === 1) return { page: "notices" };
  if (parts[0] === "schedules" && parts.length === 1) return { page: "schedules" };
  if (parts[0] === "sources" && parts.length <= 2) return parts.length === 1 ? { page: "sources" } : { page: "source", name: parts[1] };
  if ((parts[0] === "account" || parts[0] === "users" || parts[0] === "settings") &&parts.length === 1) return { page: parts[0] };
  if (parts.length === 1 && Object.hasOwn(PLANNED, parts[0])) return { page: "planned", key: parts[0] };
  if (parts[0] === "lineage" && parts.length === 1) return { page: "lineage" };
  if (parts[0] === "relations") {
    if (parts.length === 1) {
      const view = new URLSearchParams(query).get("view");
      return view === "map" ? { page: "relations", map: true } : view === "list" ? { page: "relations", list: true } : { page: "relations" };   // the list of relation cards is the default, the map is one click away
    }
    if (parts.length === 2 && parts[1] === "new") return { page: "relationnew" };   // the service refuses a relation called new, so this address is never a relation
    if (parts.length === 3 && parts[2] === "edit") return { page: "relationedit", id: parts[1] };
    if (parts.length === 2) return { page: "relation", id: parts[1] };
    return { page: "notfound" };
  }
  if (parts.length === 1 && (parts[0] === "confirm" || parts[0] === "permissions")) return { page: parts[0] };
  if (parts[0] === "confirm" && parts.length === 4 && parts[1] === "group" && /^[1-9]\d*$/.test(parts[3])) return { page: "confirmgroup", dataset: parts[2], version: Number(parts[3]) };   // what one version of a dataset moved, confirmed together
  if (parts[0] === "pipelines") {
    if (parts.length === 1) return { page: "pipelines" };
    if (parts.length === 2 && parts[1] === "new") return withDataset({ page: "pipelinenew" }, query);   // the service refuses a pipeline called new
    const view = parts[2] ?? "edit";
    if (parts.length === 2) return { page: "pipeline", name: parts[1], view };
    if (parts.length === 3 && ["runs", "history", "confirm"].includes(view)) return { page: "pipeline", name: parts[1], view };
    if (parts.length === 4 && view === "runs" && /^[1-9]\d*$/.test(parts[3])) return { page: "pipeline", name: parts[1], view: "run", run: Number(parts[3]) };
    return { page: "notfound" };
  }
  if (parts[0] === "agents" && parts.length === 1) return { page: "agents" };
  if (parts[0] === "boards") {
    if (parts.length === 1) return { page: "boards" };
    if (parts.length === 2 && parts[1] === "new") return { page: "boardnew" };   // a board's address is its number, so this one is never a board
    if (/^[1-9]\d*$/.test(parts[1] ?? "")) {
      if (parts.length === 2) return { page: "board", id: Number(parts[1]) };
      if (parts.length === 3 && parts[2] === "edit") return { page: "boardedit", id: Number(parts[1]) };
    }
    return { page: "notfound" };
  }
  if (parts[0] === "types") {
    if (parts.length === 1) return { page: "types" };
    if (parts.length === 2 && parts[1] === "new") return withDataset({ page: "typenew" }, query);   // the service refuses a type called new, so this address is never a type
    if (parts.length === 3 && parts[2] === "edit") return { page: "typeedit", id: parts[1] };
    const tab = parts[2] ?? "props";
    if (tab === "objects" && parts.length === 4 && /^[1-9]\d*$/.test(parts[3])) return { page: "object", id: parts[1], n: Number(parts[3]) };   // one object, by its row number in the data
    const p = new URLSearchParams(query).get("p");
    const q = new URLSearchParams(query).get("q");   // the explorer's query (a pivot arrives this way)
    if (parts.length <= 3 && TYPE_TABS.includes(tab)) return { page: "type", id: parts[1], tab, pageNo: /^[1-9]\d*$/.test(p ?? "") ? Number(p) : 1, ...(tab === "objects" && q ? { q } : {}) };
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

/** Where the app opens after the sign-in form: the home page. Only a session that ran out while the person was working returns to the address they were at. */
export const afterSignIn = (hash, ended) => (ended && hash && hash !== "#/" ? hash : "#/home");

/** The address of a route; the inverse of parseRoute. */
export function hrefFor(route) {
  if (route.page === "home") return "#/home";
  if (route.page === "qa") return route.id ? `#/qa/${route.id}` : route.ask ? `#/qa?ask=${encodeURIComponent(route.ask)}` : "#/qa";
  if (route.page === "tasks" || route.page === "notices" || route.page === "account" || route.page === "users" || route.page === "settings" || route.page === "sources" || route.page === "schedules") return `#/${route.page}`;
  if (route.page === "source") return `#/sources/${encodeURIComponent(route.name)}`;
  if (route.page === "planned") return `#/${route.key}`;
  if (route.page === "types") return "#/types";
  if (route.page === "confirm" || route.page === "permissions" || route.page === "lineage") return `#/${route.page}`;
  if (route.page === "confirmgroup") return `#/confirm/group/${encodeURIComponent(route.dataset)}/${route.version}`;
  if (route.page === "relations") return route.map ? "#/relations?view=map" : route.list ? "#/relations?view=list" : "#/relations";
  if (route.page === "pipelines") return "#/pipelines";
  if (route.page === "pipelinenew") return `#/pipelines/new${datasetQuery(route)}`;
  if (route.page === "pipeline") {
    const base = `#/pipelines/${encodeURIComponent(route.name)}`;
    return route.view === "run" ? `${base}/runs/${route.run}` : route.view && route.view !== "edit" ? `${base}/${route.view}` : base;
  }
  if (route.page === "relationnew") return "#/relations/new";
  if (route.page === "relation") return `#/relations/${encodeURIComponent(route.id)}`;
  if (route.page === "relationedit") return `#/relations/${encodeURIComponent(route.id)}/edit`;
  if (route.page === "typenew") return `#/types/new${datasetQuery(route)}`;
  if (route.page === "typeedit") return `#/types/${encodeURIComponent(route.id)}/edit`;
  if (route.page === "type") {
    const query = [route.pageNo > 1 ? `p=${route.pageNo}` : "", route.q ? `q=${encodeURIComponent(route.q)}` : ""].filter(Boolean).join("&");
    return `#/types/${encodeURIComponent(route.id)}/${route.tab ?? "props"}${query ? `?${query}` : ""}`;
  }
  if (route.page === "object") return `#/types/${encodeURIComponent(route.id)}/objects/${route.n}`;
  if (route.page === "agents" || route.page === "boards") return `#/${route.page}`;
  if (route.page === "boardnew") return "#/boards/new";
  if (route.page === "board") return `#/boards/${route.id}`;
  if (route.page === "boardedit") return `#/boards/${route.id}/edit`;
  if (route.page === "dataset") {
    const base = `#/datasets/${encodeURIComponent(route.name)}/${route.tab ?? "fields"}`;
    const query = [route.version ? `v=${route.version}` : "", route.pageNo > 1 ? `p=${route.pageNo}` : ""].filter(Boolean).join("&");
    return query ? `${base}?${query}` : base;
  }
  return "#/datasets";
}

// Pages not built yet: what each will do, in one line. The sidebar shows them in grey and they open a page saying exactly this.
export const PLANNED = {
};

const BUILT = { home: "#/home", qa: "#/qa", tasks: "#/tasks", notices: "#/notices", datasets: "#/datasets", types: "#/types", relations: "#/relations", lineage: "#/lineage", agents: "#/agents", boards: "#/boards", confirm: "#/confirm", users: "#/users", settings: "#/settings", permissions: "#/permissions", pipelines: "#/pipelines", sources: "#/sources", schedules: "#/schedules" };
const BUILDERS = ["tasks", "confirm", "pipelines", "sources", "schedules", "agents"];   // shown to builders and admins only: a viewer has nothing to confirm, the task list quotes keys and values and a pipeline's steps and previews quote rows (the service refuses them to a viewer)
// label (and a group's label and hint) are getters: the words are read when drawn, in the language chosen then
const item = (key, icon) => ({ key, get label() { return t(`nav.${key}`); }, icon, href: BUILT[key] ?? `#/${key}`, built: key in BUILT, builders: BUILDERS.includes(key) });
const group = (key, icon, rest) => ({ key, get label() { return t(`nav.group.${key}`); }, icon, get hint() { return t(`nav.group.${key}.hint`); }, ...rest });

/** The sidebar: a group with a `label` folds and has a grey one-line `hint`; `builders` groups are for builders and admins. A viewer sees 首页, 问数, 看板, 消息 only; every page stays reachable by its address. */
export const NAV = [
  { key: "main", items: [item("home", "home"), item("qa", "chat"), item("boards", "board"), item("notices", "bell")] },
  group("data", "database", { builders: true, items: [item("datasets", "table"), item("sources", "plug"), item("pipelines", "pipeline"), item("schedules", "clock"), item("lineage", "lineage"), item("tasks", "tasks")] }),
  group("objects", "cube", { builders: true, items: [item("confirm", "check"), item("types", "cube"), item("relations", "link")] }),
  group("apps", "apps", { builders: true, items: [item("agents", "bot")] }),
];

/** What only an admin sees. */
export const ADMIN_NAV = [group("settings", "settings", { items: [item("settings", "settings"), item("users", "users"), item("permissions", "shield")] })];

/** The groups this person's role sees, in order. */
export const navFor = (user) => [...NAV, ...(isAdmin(user) ? ADMIN_NAV : [])].filter((g) => !g.builders || canBuild(user));

/** Every page the app draws, once: the sidebar item it lives under (null: none) and the role it needs (none: anyone signed in). A new page is one entry here
 * and one view in Shell.jsx; routeModel.test.js fails when the two differ or an address opens a page that is not here. The service checks roles again. */
export const PAGES = {
  home: { nav: "home" },
  qa: { nav: "qa" },
  tasks: { nav: "tasks" },
  notices: { nav: "notices" },
  datasets: { nav: "datasets" }, dataset: { nav: "datasets" },
  pipelines: { nav: "pipelines", role: "builder" }, pipelinenew: { nav: "pipelines", role: "builder" }, pipeline: { nav: "pipelines", role: "builder" },
  sources: { nav: "sources", role: "builder" }, source: { nav: "sources", role: "builder" },
  schedules: { nav: "schedules", role: "builder" },
  types: { nav: "types" }, type: { nav: "types" }, typenew: { nav: "types" }, typeedit: { nav: "types" }, object: { nav: "types" },
  relations: { nav: "relations" }, relation: { nav: "relations" }, relationnew: { nav: "relations" }, relationedit: { nav: "relations" },
  confirm: { nav: "confirm", role: "builder" }, confirmgroup: { nav: "confirm", role: "builder" },
  agents: { nav: "agents", role: "builder" },
  boards: { nav: "boards" }, board: { nav: "boards" }, boardnew: { nav: "boards", role: "builder" }, boardedit: { nav: "boards", role: "builder" },
  lineage: { nav: "lineage" },
  settings: { nav: "settings", role: "admin" }, users: { nav: "users", role: "admin" }, permissions: { nav: "permissions", role: "admin" },
  account: { nav: null },
  planned: { nav: null },   // a page not built yet lives under its own key (navKeyOf)
};

/** Whether this person may open the page (the table's role); a page not in the table is not found, which the shell says. */
export const mayOpen = (page, user) => {
  const role = PAGES[page]?.role;
  return role === "admin" ? isAdmin(user) : role === "builder" ? canBuild(user) : true;
};

/** Which navigation item a route lives under. */
export const navKeyOf = (route) => (route.page === "planned" ? route.key : route.page in PAGES ? PAGES[route.page].nav : route.page);

/** The sidebar's word for the page a route lives under ("" when it has none). */
export const navLabelOf = (route) => [...NAV, ...ADMIN_NAV].flatMap((g) => g.items).find((i) => i.key === navKeyOf(route))?.label ?? "";

// The home page's words and decisions, as plain functions of what the service sends, so they can be tested without a browser.
import { formatDateTime, formatNumber, getLocale, t } from "./i18n/index.js";

const confirmed = (list) => (list ?? []).filter((x) => x.state === "confirmed");

/** Whether the workspace cannot answer anything yet: no dataset, or no confirmed object type. */
export const needsSetup = ({ datasets, types }) => !(datasets ?? []).length || !confirmed(types).length;

/** The four steps of 开始使用: [{key, title, text, state: "done" | "next" | "todo", button: {label, href} | null, extra?: {label, href}, note?}].
 * `users` and `sources` are null when this person may not read them (a builder cannot list users). `meId` is who is looking; `canConfirm` is whether
 * they may confirm anything now (the queue count says so; undefined when unknown). */
export function setupSteps({ datasets, types, users, role, meId = null, canConfirm }) {
  const admin = role === "admin";
  const others = (users ?? []).filter((u) => u.id !== meId);
  const done = {
    data: (datasets ?? []).length > 0,
    type: (types ?? []).length > 0,
    confirm: confirmed(types).length > 0,
    invite: others.some((u) => u.last_login_at),   // an account nobody has signed in to is not a colleague yet
  };
  const only = (datasets ?? []).length === 1 ? `?dataset=${encodeURIComponent(datasets[0].name)}` : "";
  const stuck = done.type && !done.confirm && canConfirm === false;   // proposed, and nothing here is this person's to confirm
  const steps = [
    { key: "data", title: t("home.step.data.title"), text: admin ? t("home.step.data.admin") : t("home.step.data.builder"), button: { label: t("home.step.data.button"), href: "#/datasets" } },
    { key: "type", title: t("home.step.type.title"), text: t("home.step.type.text"), button: { label: t("home.step.type.button"), href: `#/types/new${only}` } },
    stuck
      ? {
        key: "confirm", title: t("home.step.confirm.title"),
        text: admin ? t("home.step.confirm.stuckAdmin") : t("home.step.confirm.stuckBuilder"),
        button: admin ? { label: t("home.step.confirm.invite"), href: "#/users" } : { label: t("home.step.confirm.button"), href: "#/confirm" },
        ...(admin ? { extra: { label: t("home.step.confirm.queue"), href: "#/confirm" } } : {}),
      }
      : { key: "confirm", title: t("home.step.confirm.title"), text: t("home.step.confirm.text"), button: { label: t("home.step.confirm.button"), href: "#/confirm" } },
    admin
      ? { key: "invite", title: t("home.step.invite.title"), text: t("home.step.invite.admin"), button: { label: t("home.step.invite.button"), href: "#/users" }, ...(others.length && !done.invite ? { note: t("home.step.invite.note", { count: others.length }) } : {}) }
      : { key: "invite", title: t("home.step.invite.title"), text: t("home.step.invite.builder"), button: null },
  ];
  let nextFound = false;
  return steps.map((s) => {
    if (done[s.key]) {
      const { note, extra, ...rest } = s;
      return { ...rest, state: "done" };
    }
    if (!nextFound) {
      nextFound = true;
      return { ...s, state: "next" };
    }
    return { ...s, state: "todo" };
  });
}

const CJK = /[\u3400-\u9fff]/;
const plural = (w) => (/(s|x|ch|sh)$/.test(w) ? `${w}es` : /[^aeiou]y$/.test(w) ? `${w.slice(0, -1)}ies` : `${w}s`);
const cap = (w) => w.charAt(0).toUpperCase() + w.slice(1);
/** What to call a type in a question: its name, but in the English UI a Chinese-named type goes by its English name ("commit_version" → "commit versions"), never "How many 订单 are there?". */
function spoken(name, id, many) {
  if (getLocale() === "zh" || !CJK.test(name ?? "") || !id) return name;
  const words = String(id).replace(/[_-]+/g, " ").trim().toLowerCase();
  return many ? words.replace(/\S+$/, plural) : words;
}

/** Up to six questions to try, in a manager's words: "How many orders are there?" for each confirmed type, then "Orders by customer" for each confirmed relation between confirmed types. */
export function exampleQuestions(types, relations, max = 6) {
  const known = confirmed(types);
  const names = new Set(known.map((x) => x.name));
  const idOf = new Map(known.map((x) => [x.name, x.id]));
  // an English type name that is not already plural ("Order") reads "How many Order records are there?", not "How many Order are there?"
  const count = (x) => {
    const name = spoken(x.name, x.id, true);
    return t(getLocale() !== "zh" && !CJK.test(name ?? "") && !/s$/i.test(name ?? "") ? "home.example.countRecords" : "home.example.count", { name });
  };
  const counts = known.slice(0, 3).map(count);
  const by = confirmed(relations).filter((r) => names.has(r.from_name) && names.has(r.to_name)).map((r) => {
    const text = t("home.example.by", { from: spoken(r.from_name, r.from ?? idOf.get(r.from_name), true), to: spoken(r.to_name, r.to ?? idOf.get(r.to_name), false) });
    return getLocale() === "zh" ? text : cap(text);
  });
  const rest = known.slice(3).map(count);
  return [...counts, ...by, ...rest].slice(0, max);
}

/** The demo workspace (demo.py seed: 订单 confirmed, 客户 confirmed once and now waiting for a second look) offers a guest three questions with three outcomes:
 * an answer (119,810), a refusal because 客户 waits (its name and who it waits for), and another answer. null on any other workspace (the usual examples). */
export function demoQuestions(types) {
  const list = types ?? [];
  if (!list.some((x) => x.id === "order" && x.state === "confirmed")) return null;
  const waits = list.some((x) => x.id === "customer" && x.waiting);
  return [t("home.demo.answered"), ...(waits ? [t("home.demo.waiting")] : []), t("home.demo.another")];
}

/** A guest's three start cards [{key, href, icon, external?}]: the first board, why its numbers can be trusted (the confirmed view on the demo, else the board), and
 * what gets refused: on the demo the refused question asked for real, else the README. */
export function startCards(boards, types) {
  const first = boards?.dashboards?.[0];
  const board = first ? `#/boards/${first.id}` : "#/boards";
  const demo = demoQuestions(types);
  const waits = demo?.includes(t("home.demo.waiting"));
  return [
    { key: "orders", href: board, icon: "board" },
    { key: "trust", href: demo ? "#/types/order/views" : board, icon: "check-circle" },
    waits
      ? { key: "refuse", href: `#/qa?ask=${encodeURIComponent(t("home.demo.waiting"))}`, icon: "alert" }
      : { key: "refuse", href: "https://github.com/Longado/ontopoc#readme", icon: "alert", external: true },
  ];
}

/** Up to four number cards for the home page: each confirmed type that has rows, as {key, label, value, asOf, href}. `asOf` is "Data as of …" from the dataset the type reads. */
export function kpiCards(types, datasets, max = 4) {
  const when = new Map((datasets ?? []).map((d) => [d.name, d.updated_at]));
  return confirmed(types).filter((x) => Number.isInteger(x.rows)).slice(0, max).map((x) => ({
    key: x.id, label: x.name, value: formatNumber(x.rows),
    asOf: when.get(x.dataset) ? t("home.asOf", { time: formatDateTime(when.get(x.dataset)) }) : "", href: `#/types/${encodeURIComponent(x.id)}/objects`,
  }));
}

/** "Good morning, Ann" by the hour (before noon morning, before 18:00 afternoon, else evening). */
export function greeting(date, name) {
  const h = date.getHours();
  const word = t(h >= 5 && h < 12 ? "home.greeting.morning" : h >= 12 && h < 18 ? "home.greeting.afternoon" : "home.greeting.evening");
  return name ? t("home.greeting.named", { greeting: word, name }) : word;
}

/** "Data updated Nov 16, 2026, 6:30 PM": the newest dataset's time; empty with no dataset. */
export function updatedText(datasets) {
  const times = (datasets ?? []).map((d) => d.updated_at).filter(Boolean).sort();
  return times.length ? t("home.updated", { time: formatDateTime(times[times.length - 1]) }) : "";
}

/** The gate in one line for a builder or admin: object types and relations confirmed, those that need another look, and what waits for this person to confirm
 * (the queue count). [{key, count, text, href}]; null for a viewer (they are not told about definitions they cannot read, D9) and before anything is defined.
 * Read from the lists the home page already loads; the checked numbers of WP-A join it once that lands. */
export function gateStatus({ types, relations, queue = 0, mayBuild = false }) {
  const all = [...(types ?? []), ...(relations ?? [])];
  if (!mayBuild || !all.length) return null;
  const count = (state) => all.filter((x) => x.state === state).length;
  return [
    { key: "confirmed", count: count("confirmed"), href: "#/types" },
    { key: "look", count: count("needs_look"), href: "#/types" },
    { key: "queue", count: queue, href: "#/confirm" },
  ].map((x) => ({ ...x, text: t(`home.gate.${x.key}`, { count: x.count }) }));
}

/** What waits for this person, most urgent first: [{key, count, text, href}]. Only builders see the confirm queue and failed runs. */
export function todoItems({ unread = 0, queue = 0, failedRuns = 0, mayBuild = false }) {
  const items = [];
  if (mayBuild && queue > 0) items.push({ key: "queue", count: queue, text: t("home.todo.queue", { count: queue }), href: "#/confirm" });
  if (mayBuild && failedRuns > 0) items.push({ key: "failed", count: failedRuns, text: t("home.todo.failed", { count: failedRuns }), href: "#/tasks" });
  if (unread > 0) items.push({ key: "notices", count: unread, text: t("home.todo.notices", { count: unread }), href: "#/notices" });
  return items;
}

/** The team's questions of the last 7 days as the home page shows them: {figures: [{key, label, value, note}], before, held: [{key, count, text, href}]}.
 *  The answered figure carries its share of what was asked. null when there is no tally (a viewer is sent none) or nobody asked in either week. */
export function tallyView(tally) {
  const now = tally?.last_7_days, was = tally?.previous_7_days;
  if (!now || !was || now.asked + was.asked === 0) return null;
  const share = now.asked > 0 ? t("home.tally.share", { percent: `${Math.round((100 * now.answered) / now.asked)}%` }) : "";
  const figures = ["asked", "answered", "refused", "unanswered"].map((key) => ({ key, label: t(`home.tally.${key}`), value: formatNumber(now[key]), note: key === "answered" ? share : "" }));
  const held = (tally.held_back ?? []).map((d) => ({ key: d.id, count: d.questions, href: "#/confirm", text: t("home.tally.held.row", { kind: t(`ask.kind.${d.kind}`), name: d.name, count: d.questions }) }));
  return { figures, before: t("home.tally.before", { asked: formatNumber(was.asked), answered: formatNumber(was.answered) }), held };
}

/** The compact row of shortcuts a builder sees under the greeting: [{key, label, href, icon}]; nothing for a viewer. */
export const quickActions = (mayBuild) => (mayBuild ? [
  { key: "upload", label: t("home.quick.upload"), href: "#/datasets", icon: "upload" },
  { key: "pipeline", label: t("home.quick.pipeline"), href: "#/pipelines/new", icon: "pipeline" },
  { key: "type", label: t("home.quick.type"), href: "#/types/new", icon: "cube" },
  { key: "review", label: t("home.quick.review"), href: "#/confirm", icon: "check-circle" },
] : []);

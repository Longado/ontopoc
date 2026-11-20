// OntoPoc's small i18n module (no dependencies). English, or Chinese for a Chinese browser; either is a switch.
//
// HOW TO ADD AN AREA (a page or a group of pages):
//   1. Create i18n/en/<area>.js and i18n/zh/<area>.js. Each `export default` a FLAT object: { "title": "Datasets", "empty.text": "Nothing here yet." }.
//      Both files must hold exactly the same keys (i18n.test.js checks it). A plural needs key_one and key_other in both files.
//   2. Add ONE import line per language below and one entry in AREAS (the lines marked "areas").
//   3. Use it: t("<area>.title"), t("<area>.count", { count: 3 }), t("<area>.hello", { name }). Call t() while rendering (or call useT() once
//      in a component, which re-renders it when the language changes; the app root also remounts on a change, so a plain t() call is enough).
//   4. Add the converted file to i18n/converted.js: noCjk.test.js then fails if a Chinese literal is left in it (comments are fine).
//
// API: t(key, vars) · useT() (returns t, re-renders on a language change) · getLocale() · setLocale("en" | "zh") · LOCALES · formatDate(value, opts) · formatDateTime(value, opts) · formatNumber(n, opts).
// The locale is kept in localStorage "ontopoc.locale"; with nothing kept it follows the browser's languages (en when it has none of ours); "?lang=zh" (in the
// page query or after the # route) sets and keeps it.
// A key missing in the current language falls back to English, then to the key itself; the dev server logs a warning for either.
import { useSyncExternalStore } from "react";
import enAgents from "./en/agents.js"; // areas
import enAsk from "./en/ask.js"; // areas
import enBoards from "./en/boards.js"; // areas
import enNotices from "./en/notices.js"; // areas
import enAccount from "./en/account.js"; // areas
import enAuth from "./en/auth.js"; // areas
import enCommon from "./en/common.js"; // areas
import enData from "./en/data.js"; // areas
import enHome from "./en/home.js"; // areas
import enLineage from "./en/lineage.js"; // areas
import enNav from "./en/nav.js"; // areas
import enPipeline from "./en/pipeline.js"; // areas
import enSettings from "./en/settings.js"; // areas
import enShell from "./en/shell.js"; // areas
import enSources from "./en/sources.js"; // areas
import enStatus from "./en/status.js"; // areas
import enUsers from "./en/users.js"; // areas
import enSteps from "./en/steps.js"; // areas
import enUi from "./en/ui.js"; // areas
import zhAgents from "./zh/agents.js"; // areas
import zhAsk from "./zh/ask.js"; // areas
import zhBoards from "./zh/boards.js"; // areas
import zhNotices from "./zh/notices.js"; // areas
import enActions from "./en/actions.js"; // areas
import enObjects from "./en/objects.js"; // areas
import enRelations from "./en/relations.js"; // areas
import enReview from "./en/review.js"; // areas
import enTypes from "./en/types.js"; // areas
import zhAccount from "./zh/account.js"; // areas
import zhAuth from "./zh/auth.js"; // areas
import zhCommon from "./zh/common.js"; // areas
import zhData from "./zh/data.js"; // areas
import zhHome from "./zh/home.js"; // areas
import zhLineage from "./zh/lineage.js"; // areas
import zhNav from "./zh/nav.js"; // areas
import zhPipeline from "./zh/pipeline.js"; // areas
import zhSettings from "./zh/settings.js"; // areas
import zhShell from "./zh/shell.js"; // areas
import zhSources from "./zh/sources.js"; // areas
import zhStatus from "./zh/status.js"; // areas
import zhUsers from "./zh/users.js"; // areas
import zhSteps from "./zh/steps.js"; // areas
import zhUi from "./zh/ui.js"; // areas
import zhActions from "./zh/actions.js"; // areas
import zhObjects from "./zh/objects.js"; // areas
import zhRelations from "./zh/relations.js"; // areas
import zhReview from "./zh/review.js"; // areas
import zhTypes from "./zh/types.js"; // areas

/** The dictionaries: AREAS[locale][area] is a flat { key: text } object. */
export const AREAS = {
  en: { account: enAccount, actions: enActions, auth: enAuth, common: enCommon, data: enData, home: enHome, lineage: enLineage, nav: enNav, objects: enObjects, pipeline: enPipeline, relations: enRelations, review: enReview, settings: enSettings, shell: enShell, sources: enSources, status: enStatus, steps: enSteps, types: enTypes, ui: enUi, users: enUsers }, // areas
  zh: { account: zhAccount, actions: zhActions, auth: zhAuth, common: zhCommon, data: zhData, home: zhHome, lineage: zhLineage, nav: zhNav, objects: zhObjects, pipeline: zhPipeline, relations: zhRelations, review: zhReview, settings: zhSettings, shell: zhShell, sources: zhSources, status: zhStatus, steps: zhSteps, types: zhTypes, ui: zhUi, users: zhUsers }, // areas
};

Object.assign(AREAS.en, { agents: enAgents, ask: enAsk, boards: enBoards, notices: enNotices }); // areas (T3)
Object.assign(AREAS.zh, { agents: zhAgents, ask: zhAsk, boards: zhBoards, notices: zhNotices }); // areas (T3)

export const LOCALES = ["en", "zh"];
const STORAGE_KEY = "ontopoc.locale";
const INTL = { en: "en-US", zh: "zh-CN" };
const dev = () => Boolean(import.meta.env?.DEV);

const storage = () => {
  try {
    return globalThis.localStorage ?? null;
  } catch {
    return null;   // a private window may refuse
  }
};

function initialLocale() {
  const loc = globalThis.location;
  if (loc) {
    const fromUrl = new URLSearchParams(loc.search).get("lang") ?? new URLSearchParams((loc.hash.split("?")[1]) ?? "").get("lang");
    if (LOCALES.includes(fromUrl)) {
      try { storage()?.setItem(STORAGE_KEY, fromUrl); } catch { /* not remembered */ }
      return fromUrl;
    }
  }
  return pickLocale(storage()?.getItem(STORAGE_KEY), globalThis.navigator?.languages ?? [globalThis.navigator?.language]);
}

/** The language on opening: the one the person chose (stored), else the first of the browser's languages the app has (zh-CN, zh-TW: zh), else en. */
export function pickLocale(stored, languages) {
  if (LOCALES.includes(stored)) return stored;
  for (const lang of languages ?? []) {
    const base = String(lang ?? "").toLowerCase().split("-")[0];
    if (LOCALES.includes(base)) return base;
  }
  return "en";
}

let locale = initialLocale();
const listeners = new Set();
const syncHtml = () => {
  if (globalThis.document?.documentElement) globalThis.document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
};
syncHtml();

export const getLocale = () => locale;

/** Switches the language, remembers it, sets <html lang> and tells every useT() listener. An unknown locale is ignored. */
export function setLocale(next) {
  if (!LOCALES.includes(next) || next === locale) return;
  locale = next;
  try { storage()?.setItem(STORAGE_KEY, next); } catch { /* not remembered */ }
  syncHtml();
  listeners.forEach((fn) => fn());
}

const subscribe = (fn) => {
  listeners.add(fn);
  return () => listeners.delete(fn);
};

function lookup(loc, key) {
  const dot = key.indexOf(".");
  if (dot < 0) return undefined;
  return AREAS[loc]?.[key.slice(0, dot)]?.[key.slice(dot + 1)];
}

/** The text for a dotted key ("shell.search.placeholder"). `vars` fill {name}; with `count`, key_one / key_other are chosen by the locale's plural rule. */
export function t(key, vars) {
  let k = key;
  if (vars && typeof vars.count === "number") {
    const form = new Intl.PluralRules(INTL[locale]).select(vars.count);
    for (const suffix of [form, "other"]) {
      if (lookup("en", `${key}_${suffix}`) !== undefined || lookup(locale, `${key}_${suffix}`) !== undefined) {
        k = `${key}_${suffix}`;
        break;
      }
    }
  }
  let text = lookup(locale, k);
  if (text === undefined) {
    text = lookup("en", k);
    if (dev()) console.warn(text === undefined ? `[i18n] missing key "${k}"` : `[i18n] "${k}" has no ${locale} text; using English`);
  }
  if (text === undefined) return key;
  return vars ? text.replace(/\{(\w+)\}/g, (m, name) => (vars[name] === undefined ? m : String(vars[name]))) : text;
}

const bound = {};
/** A hook that re-renders the component when the language changes. Returns the t function (with `.locale` set): `const t = useT();`. */
export function useT() {
  const current = useSyncExternalStore(subscribe, getLocale, () => "en");
  bound[current] ??= Object.assign((key, vars) => t(key, vars), { locale: current });
  return bound[current];
}

const toDate = (value) => (value instanceof Date ? value : new Date(value));
const formatWith = (value, opts) => {
  const d = toDate(value);
  return Number.isNaN(d.getTime()) ? "" : new Intl.DateTimeFormat(INTL[locale], opts).format(d);
};

/** "Nov 16, 2026" (en) or "2026年11月16日" (zh); "" for a value that is not a date. */
export const formatDate = (value, opts = { year: "numeric", month: "short", day: "numeric" }) => formatWith(value, opts);
/** "Nov 16, 2026, 2:05 PM" (en); "" for a value that is not a date. */
export const formatDateTime = (value, opts = { year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) => formatWith(value, opts);
export const formatNumber = (n, opts) => (Number.isFinite(Number(n)) ? new Intl.NumberFormat(INTL[locale], opts).format(n) : "");

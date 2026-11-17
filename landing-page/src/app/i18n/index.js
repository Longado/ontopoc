// OntoPoc's small i18n module (no dependencies). English is the default; Chinese is a switch.
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
// The locale is kept in localStorage "ontopoc.locale" (default "en"); "?lang=zh" (in the page query or after the # route) sets and keeps it.
// A key missing in the current language falls back to English, then to the key itself; the dev server logs a warning for either.
import { useSyncExternalStore } from "react";
import enAgents from "./en/agents.js"; // areas
import enAsk from "./en/ask.js"; // areas
import enBoards from "./en/boards.js"; // areas
import enNotices from "./en/notices.js"; // areas
import enAccount from "./en/account.js"; // areas
import enAuth from "./en/auth.js"; // areas
import enCommon from "./en/common.js"; // areas
import enHome from "./en/home.js"; // areas
import enNav from "./en/nav.js"; // areas
import enSettings from "./en/settings.js"; // areas
import enShell from "./en/shell.js"; // areas
import enStatus from "./en/status.js"; // areas
import enUi from "./en/ui.js"; // areas
import zhAgents from "./zh/agents.js"; // areas
import zhAsk from "./zh/ask.js"; // areas
import zhBoards from "./zh/boards.js"; // areas
import zhNotices from "./zh/notices.js"; // areas
import zhAccount from "./zh/account.js"; // areas
import zhAuth from "./zh/auth.js"; // areas
import zhCommon from "./zh/common.js"; // areas
import zhHome from "./zh/home.js"; // areas
import zhNav from "./zh/nav.js"; // areas
import zhSettings from "./zh/settings.js"; // areas
import zhShell from "./zh/shell.js"; // areas
import zhStatus from "./zh/status.js"; // areas
import zhUi from "./zh/ui.js"; // areas

/** The dictionaries: AREAS[locale][area] is a flat { key: text } object. */
export const AREAS = {
  en: { account: enAccount, auth: enAuth, common: enCommon, home: enHome, nav: enNav, settings: enSettings, shell: enShell, status: enStatus, ui: enUi }, // areas
  zh: { account: zhAccount, auth: zhAuth, common: zhCommon, home: zhHome, nav: zhNav, settings: zhSettings, shell: zhShell, status: zhStatus, ui: zhUi }, // areas
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
  const stored = storage()?.getItem(STORAGE_KEY);
  return LOCALES.includes(stored) ? stored : "en";
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

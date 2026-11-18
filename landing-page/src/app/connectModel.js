// The connection guide's words, as plain data so they can be tested without a browser: the steps, what a failed connection most likely means and how to check it,
// and the text a person copies to send to their DBA. The service words each failure in one sentence (source_connect.describe); `diagnose` reads that sentence
// (the patterns it looks for are in serverWords.js).
import { t } from "./i18n/index.js";
import { CONNECT_PATTERNS } from "./serverWords.js";
import { TLS_MODES, kindPort } from "./sourceModel.js";

/** The five steps of the guide, with their names in the current language. */
export const STEPS = ["type", "connect", "test", "tables", "schedule"].map((key) => ({ key, get label() { return t(`sources.step.${key}`); } }));

/** The five things the guide names when a connection fails; each has a cause below. */
export const CHECKS = ["host", "port", "password", "cert", "timeout"];

/** Switching the type puts that type's usual port in the box. */
export const portAfterKind = (kind) => String(kindPort(kind));

// Each failure: its kind and its causes, as [what, check] text keys.
const NETWORK = ["sources.conn.net.what", "sources.conn.net.check"];
const own = (kind, ...numbers) => numbers.map((n) => [`sources.conn.${kind}.${n}.what`, `sources.conn.${kind}.${n}.check`]);
const CAUSES = {
  host: own("host", 1, 2),
  blocked: own("blocked", 1),
  driver: own("driver", 1),
  cert: own("cert", 1, 2),
  tls: own("tls", 1),
  password: own("password", 1, 2),
  database: own("database", 1),
  timeout: [["sources.conn.timeout.1.what", NETWORK[1]], ...own("timeout", 2)],
  port: [...own("port", 1, 2), NETWORK],
  other: [...own("other", 1), NETWORK, ...own("other", 2)],
};

/** What a failed connection most likely means: {kind, title, causes: [{what, check}]}, from the sentence the service sent. Anything not recognised gets the general checks. */
export function diagnose(message) {
  const text = String(message ?? "");
  const kind = CONNECT_PATTERNS.find(([, test]) => test.test(text))?.[0] ?? "other";
  return { kind, title: t(`sources.conn.${kind}.title`), causes: CAUSES[kind].map(([what, check]) => ({ what: t(what), check: t(check) })) };
}

const tlsWord = (tls) => TLS_MODES.find((m) => m.key === tls)?.label ?? tls;

/** The text for "Copy error details": enough for a DBA to act on, and never the password. */
export function errorReport({ source, kind, host, port, database, username, tls, message, at }) {
  return [
    t("sources.report.title", { at: at ? t("sources.report.at", { at }) : "" }),
    t("sources.report.source", { value: source }),
    t("sources.report.type", { value: kind }),
    t("sources.report.address", { value: `${host}:${port}` }),
    t("sources.report.database", { value: database }),
    t("sources.report.username", { value: username }),
    t("sources.report.encryption", { value: tlsWord(tls) }),
    t("sources.report.error", { value: message }),
  ].join("\n");
}

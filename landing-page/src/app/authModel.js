import { t } from "./i18n/index.js";

// What a signed-in person is and may do, as plain data so it can be tested without a browser. The service decides; these only choose what to show.
/** Role names in the current language (read at use time, so a language switch shows at once). */
export const ROLE_LABEL = { get viewer() { return t("auth.role.viewer"); }, get builder() { return t("auth.role.builder"); }, get admin() { return t("auth.role.admin"); } };
export const ROLES = ["viewer", "builder", "admin"];
const RANK = { viewer: 1, builder: 2, admin: 3 };

export const roleLabel = (role) => ROLE_LABEL[role] ?? role;

/** Whether the person's role changes data and definitions (upload, delete). A viewer reads and asks. */
export const canBuild = (user) => RANK[user?.role] >= RANK.builder;
export const isAdmin = (user) => user?.role === "admin";

/** A demo guest: signed in through "Try the demo", read-only, with a limited number of questions. */
export const isGuest = (user) => user?.provider === "demo";

/** Where "Request access" goes: the service's own feedback address when it has one, else the project's issue page. */
export const DEFAULT_ACCESS_URL = "https://github.com/Longado/ontopoc/issues/new";
export const accessUrl = (feedbackUrl) => (typeof feedbackUrl === "string" && feedbackUrl.trim() ? feedbackUrl.trim() : DEFAULT_ACCESS_URL);

/** The top search box's hint: a viewer has boards and questions, a builder has datasets, types and pipelines. */
export const searchPlaceholder = (user) => (user?.role === "viewer" ? t("shell.search.viewer") : t("shell.search.builder"));

/** One account's state in a word: disabled, waiting to change the first password, or fine. */
export const statusText = (user) => (user.disabled ? t("auth.account.disabled") : user.must_change ? t("auth.account.mustChange") : t("auth.account.active"));

/** The two-person line on the users page: whether it is on and whether it is in force now. */
export function twoPersonText(rule) {
  if (!rule.enabled) return t("auth.twoPerson.off");
  if (!rule.active) return t("auth.twoPerson.inactive", { count: rule.builders });
  return t("auth.twoPerson.active", { count: rule.builders });
}

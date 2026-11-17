// The users page's words and small decisions, as plain data so they can be tested without a browser.
import { roleLabel } from "./authModel.js";
import { t } from "./i18n/index.js";

/** The three roles with what each may do, in the current language (getters: read at use time). */
export const ROLE_CARDS = ["viewer", "builder", "admin"].map((key) => ({ key, get label() { return roleLabel(key); }, get rights() { return t(`users.role.${key}.rights`); } }));

const LOWER = "abcdefghijkmnpqrstuvwxyz";   // no l, o
const UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ";   // no I, O
const DIGITS = "23456789";                   // no 0, 1

/** A first password of 16 characters with lower case, upper case and digits and no look-alike characters (it is read aloud and typed). `rand` is Math.random, or a stand-in in tests; in a
 * browser the caller passes a function over crypto.getRandomValues. */
export function randomPassword(rand = Math.random) {
  const pick = (set) => set[Math.floor(rand() * set.length)];
  const all = LOWER + UPPER + DIGITS;
  const chars = [pick(LOWER), pick(UPPER), pick(DIGITS), ...Array.from({ length: 13 }, () => pick(all))];
  for (let i = chars.length - 1; i > 0; i -= 1) {   // shuffle, so the first three are not always lower, upper, digit
    const j = Math.floor(rand() * (i + 1));
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  return chars.join("");
}

/** A random function over the browser's secure random numbers. */
export const secureRandom = () => {
  const [n] = crypto.getRandomValues(new Uint32Array(1));
  return n / 2 ** 32;
};

/** The message to send a new colleague: where to log in, the account and the first password. */
export function inviteText({ origin, username, display_name, password, role }) {
  return [
    t("users.invite.hello", { name: display_name || username, role: roleLabel(role) }),
    t("users.invite.url", { origin }),
    t("users.invite.username", { username }),
    t("users.invite.password", { password }),
    t("users.invite.change"),
  ].join("\n");
}

export const MIN_PASSWORD = 12;

/** What is missing from the new-user form; "" when nothing. */
export function newUserProblem(f) {
  if (!String(f.username ?? "").trim()) return t("users.problem.username");
  if (String(f.password ?? "").length < MIN_PASSWORD) return t("users.problem.password", { min: MIN_PASSWORD });
  return "";
}

/** The two-person rule as a banner: {tone: off | waiting | on, text (the state, whole), from (what changes from now on, one line)}. */
export function twoPersonBanner(tp) {
  if (!tp.enabled) {
    return { tone: "off", text: t("users.two.off.text"), from: t("users.two.off.from") };
  }
  if (!tp.active) {
    return {
      tone: "waiting",
      text: t("users.two.waiting.text", { count: tp.builders }),
      from: t("users.two.waiting.from"),
    };
  }
  return {
    tone: "on",
    text: t("users.two.on.text", { count: tp.builders }),
    from: t("users.two.on.from"),
  };
}

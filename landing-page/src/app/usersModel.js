// The users page's words and small decisions, as plain data so they can be tested without a browser.
import { roleLabel } from "./authModel.js";

export const ROLE_CARDS = [
  { key: "viewer", label: "查看者", rights: "只能看和提问，看不到原始数据行" },
  { key: "builder", label: "建设者", rights: "还能上传数据、建和改对象类型、管道，并确认别人建的" },
  { key: "admin", label: "管理员", rights: "再加管理用户、连接数据库、设置权限" },
];

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
    `${display_name || username}，你好。我给你开了 OntoPoc 的账号（${roleLabel(role)}）：`,
    `登录地址：${origin}`,
    `账号：${username}`,
    `初始密码：${password}`,
    "第一次登录时系统会要你改一个新密码，请改掉初始密码。",
  ].join("\n");
}

export const MIN_PASSWORD = 12;

/** What is missing from the new-user form; "" when nothing. */
export function newUserProblem(f) {
  if (!String(f.username ?? "").trim()) return "要填账号";
  if (String(f.password ?? "").length < MIN_PASSWORD) return `初始密码至少 ${MIN_PASSWORD} 个字符`;
  return "";
}

/** The two-person rule as a banner: {tone: off | waiting | on, text (the state, whole), from (what changes from now on, one line)}. */
export function twoPersonBanner(t) {
  if (!t.enabled) {
    return { tone: "off", text: "两人确认：关着。一个人建的东西，自己确认就算数。", from: "从现在起：谁建的都可以自己确认，没有第二个人把关。" };
  }
  if (!t.active) {
    return {
      tone: "waiting",
      text: `两人确认：开着，但现在能确认的只有 ${t.builders} 人，所以暂时自己确认自己建的也算数。有第二个人能确认时，自动按两人确认来`,
      from: "从现在起：再加一位建设者，两人确认就自动生效。",
    };
  }
  return {
    tone: "on",
    text: `两人确认：开着。一个人建的东西，要另一个建设者确认才算数。现在能确认的有 ${t.builders} 人`,
    from: "从现在起：谁建的，谁不能自己确认，要由另一位建设者确认。",
  };
}

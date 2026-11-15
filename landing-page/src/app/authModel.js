// What a signed-in person is and may do, as plain data so it can be tested without a browser. The service decides; these only choose what to show.
export const ROLE_LABEL = { viewer: "查看者", builder: "建设者", admin: "管理员" };
export const ROLES = ["viewer", "builder", "admin"];
const RANK = { viewer: 1, builder: 2, admin: 3 };

export const roleLabel = (role) => ROLE_LABEL[role] ?? role;

/** Whether the person's role changes data and definitions (upload, delete). A viewer reads and asks. */
export const canBuild = (user) => RANK[user?.role] >= RANK.builder;
export const isAdmin = (user) => user?.role === "admin";

/** One account's state in a word: disabled, waiting to change the first password, or fine. */
export const statusText = (user) => (user.disabled ? "已停用" : user.must_change ? "要先改初始密码" : "正常");

/** The two-person line on the users page: whether it is on and whether it is in force now. */
export function twoPersonText(t) {
  if (!t.enabled) return "两人确认：关着。一个人建的东西，自己确认就算数";
  if (!t.active) return `两人确认：开着，但现在能确认的只有 ${t.builders} 人，所以暂时自己确认自己建的也算数。有第二个人能确认时，自动按两人确认来`;
  return `两人确认：开着。一个人建的东西，要另一个建设者确认才算数。现在能确认的有 ${t.builders} 人`;
}

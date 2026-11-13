// What a signed-in person is and may do, as plain data so it can be tested without a browser. The service decides; these only choose what to show.
export const ROLE_LABEL = { viewer: "查看", builder: "建设", admin: "管理员" };
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
  if (!t.enabled) return "两人确认：已关闭，一个人可以确认自己提的定义";
  const who = `现在有 ${t.builders} 人能确认`;
  return t.active ? `两人确认：已开启，${who}，生效中` : `两人确认：已开启，但${who}，暂不生效（有第二个人能确认就自动生效）`;
}

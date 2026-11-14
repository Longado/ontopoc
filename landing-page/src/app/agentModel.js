// The agent page: what an outside agent is told to run, as plain functions of what the service sends.

export const TOKEN_PLACEHOLDER = "<在下面创建令牌后填这里>";

/** The entry an MCP client puts in its settings to start the server as the person the token belongs to, from the installed package. `local` adds this machine's code path (the admin's, for a machine that has not installed the package). With a token the server offers the read-only tools unless told otherwise. */
export function connectConfig({ command, origin, token, local = false }) {
  const env = { ONTOPOC_URL: origin, ONTOPOC_TOKEN: token || TOKEN_PLACEHOLDER };
  return JSON.stringify({
    mcpServers: {
      ontopoc: {
        command: command.python,
        args: ["-m", command.module],
        env: local && command.local_src ? { PYTHONPATH: command.local_src, ...env } : env,
      },
    },
  }, null, 2);
}

/** A tool's first sentence: what it does, without the notes after it. */
export const firstSentence = (text) => text.split(/[。\n]/)[0];

/** What the skill folder holds, in one line. */
export const skillText = (skill) => `${skill.types} 个对象类型、${skill.relations} 条关系、${skill.views} 个视图、${skill.derived} 个派生属性；都是已确认的，没有数据行`;

export const SCOPES = [["read", "只读：读定义和数据行、提问；不能上传、确认、改"], ["all", "全部：和主人在页面上能做的一样"]];
export const EXPIRY_DAYS = [7, 30, 90, 365];

/** A token's reach in a word. */
export const scopeWord = (t) => (t.scope === "all" ? "全部" : "只读");

/** When a token ends: its day, or that it has ended already; a token made before expiry existed has no end. */
export const endText = (t) => (!t.expires_at ? "不过期" : t.expired ? "已过期" : t.expires_at.slice(0, 10));

/** A token's state in a word. */
export const tokenState = (t) => (t.revoked ? "已撤销" : t.expired ? "已过期" : t.last_used_at ? "在用" : "还没用过");

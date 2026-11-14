// The agent page: what an outside agent is told to run, as plain functions of what the service sends.

export const TOKEN_PLACEHOLDER = "<在下面创建令牌后填这里>";

/** The entry an MCP client puts in its settings to start the server as the person the token belongs to. Read-only tools only. */
export function connectConfig({ command, origin, token }) {
  return JSON.stringify({
    mcpServers: {
      ontopoc: {
        command: command.python,
        args: ["-m", command.module],
        env: { PYTHONPATH: command.src, ONTOPOC_URL: origin, ONTOPOC_TOOLSET: "read", ONTOPOC_TOKEN: token || TOKEN_PLACEHOLDER },
      },
    },
  }, null, 2);
}

/** A tool's first sentence: what it does, without the notes after it. */
export const firstSentence = (text) => text.split(/[。\n]/)[0];

/** What the skill folder holds, in one line. */
export const skillText = (skill) => `${skill.types} 个对象类型、${skill.relations} 条关系、${skill.views} 个视图、${skill.derived} 个派生属性；都是已确认的，没有数据行`;

/** A token's state in a word. */
export const tokenState = (t) => (t.revoked ? "已撤销" : t.last_used_at ? "在用" : "还没用过");

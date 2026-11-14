import React, { useState } from "react";
import { SKILL_HREF, createAgentToken, getAgentInfo, getAgentTokens, getUsers, revokeAgentToken } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { isAdmin, roleLabel } from "./authModel.js";
import { connectConfig, firstSentence, skillText, tokenState } from "./agentModel.js";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";

/** Tokens that act as a named person: the admin makes one here, it is shown once, and can be revoked. */
function Tokens({ onMade }) {
  const [tokens, reload] = useLoad(() => getAgentTokens(), []);
  const [users] = useLoad(() => getUsers(), []);
  const [who, setWho] = useState("");
  const [label, setLabel] = useState("");
  const [made, setMade] = useState(null);
  const [error, setError] = useState("");
  const active = (users.data ?? []).filter((u) => !u.disabled);
  const create = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const body = await createAgentToken(Number(who), label.trim());
      setMade(body);
      onMade(body.token);
      setLabel("");
      reload();
    } catch (err) {
      setError(err.message);
    }
  };
  const revoke = async (id) => {
    setError("");
    try {
      await revokeAgentToken(id);
      setMade(null);
      onMade("");
      reload();
    } catch (err) {
      setError(err.message);
    }
  };
  return (
    <>
      <h2 className="section">令牌</h2>
      <p className="muted">智能体以令牌的主人的身份看：他的角色，他看得到的类型和行。令牌只在创建时显示一次。</p>
      <form onSubmit={create} className="inline wide">
        <Select label="以谁的身份" value={who} onChange={setWho}>
          <option value="">选一个人</option>
          {active.map((u) => <option key={u.id} value={u.id}>{u.display_name}（{roleLabel(u.role)}）</option>)}
        </Select>
        <input type="text" aria-label="令牌用途" placeholder="用来做什么，例如 客服助手" value={label} onChange={(e) => setLabel(e.target.value)} />
        <button className="secondary" type="submit" disabled={!who || !label.trim()}>创建令牌</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {made && (
        <p className="token">
          <span className="caption">现在复制，之后看不到了（{made.display_name} 的令牌）：</span>
          <input type="text" readOnly value={made.token} aria-label="新令牌" onFocus={(e) => e.target.select()} />
        </p>
      )}
      {tokens.status === "error" && <p className="error">{tokens.error}</p>}
      {(tokens.data ?? []).length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>以谁的身份</th><th>用途</th><th>创建</th><th>最近用过</th><th></th></tr></thead>
            <tbody>
              {tokens.data.map((t) => (
                <tr key={t.id}>
                  <td>{t.display_name} <span className="muted small">{roleLabel(t.role)}</span></td>
                  <td>{t.label}</td>
                  <td>{timeText(t.created_at)}</td>
                  <td>{t.last_used_at ? timeText(t.last_used_at) : <span className="faint">没用过</span>}</td>
                  <td>{t.revoked ? <span className="muted">{tokenState(t)}</span> : <button className="plain" onClick={() => revoke(t.id)}>撤销</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

export function AgentsPage() {
  const { user } = useAuth();
  const [info] = useLoad(() => getAgentInfo(), []);
  const [token, setToken] = useState("");
  const [copied, setCopied] = useState(false);
  const i = info.data;
  const config = i ? connectConfig({ command: i.command, origin: window.location.origin, token }) : "";
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(config);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };
  return (
    <main className="page">
      <h1 tabIndex={-1}>智能体</h1>
      {info.status === "error" && <p className="error">{info.error}</p>}
      {i && (
        <>
          <h2 className="section">能调用什么</h2>
          <div className="table-wrap">
            <table className="wraps">
              <thead><tr><th>工具</th><th>做什么</th><th>参数</th></tr></thead>
              <tbody>
                {i.tools.map((t) => (
                  <tr key={t.name}>
                    <td className="keep"><code>{t.name}</code></td>
                    <td>{firstSentence(t.description)}</td>
                    <td>{t.arguments.length ? t.arguments.map((a) => `${a.name}${a.required ? "" : "（可选）"}`).join("、") : <span className="faint">没有</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="muted small">带令牌连上来时默认只给这几个，都是只读的：不能上传、不能确认、不能改。问答被拒绝时，原因原样转告，不会给一个猜的答案。</p>
          <p className="muted small">在连接配置的 env 里加 <code>"ONTOPOC_TOOLSET": "all"</code> 会再多 {i.more_with_all} 个工具：上传数据、建模、确认、存规则、导出等，能做的仍受令牌主人的角色限制。给外部智能体不建议加。</p>
          <h2 className="section">怎么连</h2>
          <p className="muted">把这一段放进支持 MCP 的客户端的设置里。令牌在下面创建。</p>
          <pre className="code-box">{config}</pre>
          <div className="inline"><button className="secondary" onClick={copy}>{copied ? "已复制" : "复制"}</button></div>
          {isAdmin(user) ? <Tokens onMade={setToken} /> : <p className="muted">令牌由管理员在这里创建。</p>}
          <h2 className="section">技能包</h2>
          <p className="muted">{skillText(i.skill)}。</p>
          <div className="inline"><a className="button secondary" href={SKILL_HREF} download={i.skill.file}>下载技能包（zip）</a></div>
        </>
      )}
      {!i && info.status === "loading" && <p className="muted">加载中</p>}
    </main>
  );
}

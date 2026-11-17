import React, { useState } from "react";
import { SKILL_HREF, createAgentToken, getAgentInfo, getAgentTokens, getUsers, revokeAgentToken } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { FormDialog } from "./FormDialog.jsx";
import { isAdmin, roleLabel } from "./authModel.js";
import { EXPIRY_DAYS, SCOPES, connectConfig, endText, firstSentence, scopeWord, skillText, tokenState } from "./agentModel.js";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";

/** Tokens that act as a named person: the admin makes one here, it is shown once, and can be revoked. */
function Tokens({ onMade }) {
  const [tokens, reload] = useLoad(() => getAgentTokens(), []);
  const [users] = useLoad(() => getUsers(), []);
  const [who, setWho] = useState("");
  const [label, setLabel] = useState("");
  const [scope, setScope] = useState("read");
  const [days, setDays] = useState("90");
  const [made, setMade] = useState(null);
  const [error, setError] = useState("");
  const [revoking, setRevoking] = useState(null);   // the token the admin is about to revoke
  const [revoked, setRevoked] = useState(false);
  const active = (users.data ?? []).filter((u) => !u.disabled && u.role !== "admin");   // an admin's account gets no token: a leaked one would be the whole service
  const create = async (e) => {
    e.preventDefault();
    setError("");
    try {
      const body = await createAgentToken(Number(who), label.trim(), scope, Number(days));
      setMade(body);
      onMade(body.token);
      setLabel("");
      reload();
    } catch (err) {
      setError(err.message);
    }
  };
  const revoke = async (id) => {
    await revokeAgentToken(id);
    setMade(null);
    onMade("");
    setRevoked(true);
    reload();
  };
  return (
    <>
      <h2 className="section">令牌</h2>
      <p className="muted">智能体以令牌的主人的身份看：他看得到的类型和行。只读令牌只能读和提问，管理员的账号不发令牌。令牌只在创建时显示一次，到期后失效。</p>
      <form onSubmit={create} className="inline wide token-form">
        <Select label="以谁的身份" value={who} onChange={setWho}>
          <option value="">选一个人</option>
          {active.map((u) => <option key={u.id} value={u.id}>{u.display_name}（{roleLabel(u.role)}）</option>)}
        </Select>
        <input type="text" aria-label="令牌用途" placeholder="用来做什么，例如 客服助手" value={label} onChange={(e) => setLabel(e.target.value)} />
        <Select label="权限" value={scope} onChange={setScope}>
          {SCOPES.map(([k, text]) => <option key={k} value={k}>{text}</option>)}
        </Select>
        <Select label="有效期" value={days} onChange={setDays}>
          {EXPIRY_DAYS.map((d) => <option key={d} value={d}>{d} 天</option>)}
        </Select>
        <button className="secondary" type="submit" disabled={!who || !label.trim()}>创建令牌</button>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
      {revoked && <p className="ok" role="status">已撤销</p>}
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
            <thead><tr><th>以谁的身份</th><th>用途</th><th>权限</th><th>到期</th><th>最近用过</th><th></th></tr></thead>
            <tbody>
              {tokens.data.map((t) => (
                <tr key={t.id}>
                  <td>{t.display_name} <span className="muted small">{roleLabel(t.role)}</span></td>
                  <td>{t.label}</td>
                  <td>{scopeWord(t)}</td>
                  <td>{endText(t)}</td>
                  <td>{t.last_used_at ? timeText(t.last_used_at) : <span className="faint">没用过</span>}</td>
                  <td>{t.revoked || t.expired ? <span className="muted">{tokenState(t)}</span> : <button className="plain" onClick={() => { setRevoked(false); setRevoking(t); }}>撤销</button>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {revoking && (
        <FormDialog title="撤销这个令牌" submitLabel="确认撤销" valid onClose={() => setRevoking(null)} onSubmit={() => revoke(revoking.id)}>
          <p>“{revoking.label}”（{revoking.display_name} 的令牌）马上失效，用它的智能体会被拒绝。撤销后不能恢复，要用就得重新创建一个。</p>
        </FormDialog>
      )}
    </>
  );
}

export function AgentsPage() {
  const { user } = useAuth();
  const [info] = useLoad(() => getAgentInfo(), []);
  const [token, setToken] = useState("");
  const i = info.data;
  const config = i ? connectConfig({ command: i.command, origin: window.location.origin, token }) : "";
  const localConfig = i?.command.local_src ? connectConfig({ command: i.command, origin: window.location.origin, token, local: true }) : "";
  const [copied, setCopied] = useState("");
  const copy = async (which, text) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
    } catch {
      setCopied("");
    }
  };
  return (
    <main className="page">
      <h1 tabIndex={-1}>AI 工具接入</h1>
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
          <p className="muted small">连上来的工具跟着令牌的权限走，由服务判定：只读令牌只有这几个，都是只读的，不能上传、不能确认、不能改。问答被拒绝时，原因原样转告，不会给一个猜的答案。</p>
          <p className="muted small">创建令牌时选“全部”，会再多 {i.more_with_all} 个工具：上传数据、建模、确认、存规则、导出等，能做的仍受令牌主人的角色限制。不建议给外部智能体。</p>
          <h2 className="section">怎么连</h2>
          <p className="muted">在要连上来的电脑上先装好 ontopoc 这个包，再把这一段放进支持 MCP 的客户端的设置里。服务地址已经写好。令牌在下面创建。</p>
          <pre className="code-box">{config}</pre>
          <div className="inline"><button className="secondary" onClick={() => copy("generic", config)}>{copied === "generic" ? "已复制" : "复制"}</button></div>
          {localConfig && (
            <>
              <h3 className="item-title">本机</h3>
              <p className="muted small">只有管理员看得到。这台机器上没装包、直接跑源码时用这一段，多一行代码所在的目录。</p>
              <pre className="code-box">{localConfig}</pre>
              <div className="inline"><button className="secondary" onClick={() => copy("local", localConfig)}>{copied === "local" ? "已复制" : "复制"}</button></div>
            </>
          )}
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

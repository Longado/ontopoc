import React from "react";
import { getAsk, getHealth, getTwoPerson } from "./api.js";
import { BACKUP_FILES, workspaceRows } from "./settingsModel.js";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { StatusChip } from "./ui/StatusChip.jsx";

const CHIP = { ok: ["confirmed", "正常"], warn: ["look", "要处理"], unknown: ["draft", "未知"] };

/** Reads what the workspace is set up with; a part this service will not tell comes back as null instead of failing the page. */
async function loadSettings() {
  const ok = (p) => p.then((v) => v, () => null);
  const [ask, two, health] = await Promise.all([ok(getAsk()), ok(getTwoPerson()), ok(getHealth())]);
  return { modelReady: typeof ask?.model_ready === "boolean" ? ask.model_ready : null, twoPerson: two, health };
}

/** 设置 · 工作区 (admin): whether questions can be answered, the two-person rule, the running build, and what to back up. Read only: each setting changes where it lives. */
export function SettingsPage() {
  const [state] = useLoad(loadSettings, []);
  const rows = state.data ? workspaceRows(state.data) : [];
  return (
    <main className="page settings">
      <PageHeader crumbs={[{ label: "设置" }, { label: "工作区" }]} title="设置 · 工作区" sub="这个工作区现在是什么状态，以及要自己留意什么。" />
      <section className="card" aria-labelledby="ws-title">
        <h2 id="ws-title">运行状态</h2>
        {!state.data ? <p className="muted">加载中</p> : (
          <ul className="setting-rows">
            {rows.map((r) => (
              <li key={r.key} className="setting-row">
                <div className="setting-name"><strong>{r.title}</strong><StatusChip state={CHIP[r.state][0]} label={CHIP[r.state][1]} /></div>
                <p className="muted">{r.text}{r.link && <> <a href={r.link.href}>{r.link.label}</a></>}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
      <section className="card" aria-labelledby="backup-title">
        <h2 id="backup-title">备份</h2>
        <p className="muted">数据目录里这两个文件要一起备份，备份放在只有自己能读的地方。</p>
        <div className="table-wrap">
          <table>
            <thead><tr><th>文件</th><th>是什么</th></tr></thead>
            <tbody>{BACKUP_FILES.map((f) => <tr key={f.file}><td><code>{f.file}</code></td><td>{f.what}</td></tr>)}</tbody>
          </table>
        </div>
        <p className="muted">备份时先停服务，或用 <code>sqlite3 workspace.sqlite ".backup /path/backup.sqlite"</code>。拷走 workspace.sqlite 等于把密码哈希交了出去，别放在共享盘上。详见 docs/DEPLOY.md 第 4 节。</p>
      </section>
    </main>
  );
}

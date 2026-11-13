import React, { useState } from "react";
import { csvHref, getDataset } from "./api.js";
import { DeleteDialog } from "./DeleteDialog.jsx";
import { isNumeric, keyText, originText, percentText, timeText, typeLabel } from "./format.js";
import { Select } from "./Select.jsx";
import { TABS, TAB_LABEL, hrefFor } from "./routeModel.js";
import { UploadDialog } from "./UploadDialog.jsx";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { useLoad } from "./useLoad.js";
import { keyListText, noChangeText, timeline, versionChangeText, versionWay } from "./versionText.js";

function Fields({ page }) {
  const multi = page.key_checks.filter((c) => c.columns.length > 1);
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>列名</th><th>类型</th><th className="num">填写率</th><th>主键检查</th></tr>
          </thead>
          <tbody>
            {page.columns.map((c) => (
              <tr key={c.name}>
                <td>{c.name}</td>
                <td>{typeLabel(c.type)}</td>
                <td className="num" title={c.missing ? `缺 ${c.missing} 行` : undefined}>{percentText(c.fill_rate)}</td>
                <td className={c.key_check?.status === "failed" || (c.near_key && !c.possible_key) ? "bad" : c.possible_key || c.key_check ? "" : "muted"}>{keyText(c)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {multi.length > 0 && (
        <ul className="checks">
          {multi.map((c) => (
            <li key={c.id} className={c.status === "failed" ? "bad" : ""}>
              {c.columns.join(" + ")}：{c.status === "passed" ? "没有重复，没有空值" : `重复 ${c.violations} 行，空 ${c.null_key_rows} 行`}（查了 {c.rows_checked} 行）
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function Preview({ page, name }) {
  const { preview } = page;
  const at = (n) => hrefFor({ page: "dataset", name, tab: "preview", version: page.version === page.current_version ? null : page.version, pageNo: n });
  const numeric = page.columns.map((c) => isNumeric(c.type));
  return (
    <>
      <div className="toolbar">
        <Select label="版本" value={String(page.version)} onChange={(v) => { window.location.hash = hrefFor({ page: "dataset", name, tab: "preview", version: Number(v) === page.current_version ? null : Number(v) }); }}>
          {page.versions.map((v) => (
            <option key={v.version} value={v.version}>第 {v.version} 版{v.current ? "（当前）" : ""}</option>
          ))}
        </Select>
        <span className="muted">
          第 {(preview.page - 1) * preview.limit + (preview.total ? 1 : 0)}–{Math.min(preview.page * preview.limit, preview.total)} 行，共 {preview.total} 行
        </span>
        <a className="download" href={csvHref(name, page.version === page.current_version ? null : page.version)} download>下载 CSV</a>
      </div>
      <div className="table-wrap tall">
        <table>
          <thead>
            <tr>{preview.columns.map((c, i) => <th key={c} className={numeric[i] ? "num" : ""}>{c}</th>)}</tr>
          </thead>
          <tbody>
            {preview.rows.map((row, r) => (
              <tr key={r}>
                {row.map((cell, i) => (
                  <td key={i} className={`${numeric[i] ? "num " : ""}cell`} title={cell ?? undefined}>{cell ?? <span className="faint">—</span>}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {preview.pages > 1 && (
        <nav className="pager" aria-label="预览分页">
          {preview.page > 1 ? <a href={at(preview.page - 1)}>上一页</a> : <span className="faint">上一页</span>}
          <span>{preview.page} / {preview.pages}</span>
          {preview.page < preview.pages ? <a href={at(preview.page + 1)}>下一页</a> : <span className="faint">下一页</span>}
        </nav>
      )}
    </>
  );
}

function Versions({ page, name }) {
  const rows = timeline(page.versions, page.no_change_updates);
  return (
    <div className="table-wrap">
      <table className="wraps">
        <thead>
          <tr><th>版本</th><th>时间</th><th>操作人</th><th>方式</th><th>变化</th><th></th></tr>
        </thead>
        <tbody>
          {rows.map((r, i) =>
            r.type === "no_change" ? (
              <tr key={`skip-${i}`} className="note">
                <td></td>
                <td>{timeText(r.at)}</td>
                <td className="keep">{r.who}</td>
                <td colSpan={3}>{noChangeText(r)}</td>
              </tr>
            ) : (
              <tr key={r.version}>
                <td>第 {r.version} 版{r.current && <span className="here"> 当前</span>}</td>
                <td>{timeText(r.at)}</td>
                <td className="keep">{r.who ?? <span className="faint">—</span>}</td>
                <td className="keep">{versionWay(r)}</td>
                <td>
                  {versionChangeText(r)}
                  {(r.changed_keys.length > 0 || r.added_keys.length > 0) && (
                    <details className="which">
                      <summary>看是哪些行</summary>
                      {r.changed_keys.length > 0 && <p>改的行：{keyListText(r.changed_keys, r.changed)}</p>}
                      {r.added_keys.length > 0 && <p>增的行：{keyListText(r.added_keys, r.added)}</p>}
                    </details>
                  )}
                </td>
                <td className="keep"><a href={hrefFor({ page: "dataset", name, tab: "preview", version: r.current ? null : r.version })}>预览</a></td>
              </tr>
            ),
          )}
        </tbody>
      </table>
    </div>
  );
}

export function DatasetPage({ route }) {
  const { name, tab, version, pageNo } = route;
  const [state, reload] = useLoad(() => getDataset(name, version, pageNo), [name, version, pageNo]);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const mayBuild = canBuild(useAuth().user);
  const page = state.data;
  const at = (t) => hrefFor({ page: "dataset", name, tab: t, version });
  return (
    <main className="page">
      <a className="back" href="#/datasets">
        <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M7.5 2.5 4 6l3.5 3.5" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" /></svg>
        数据集
      </a>
      <div className="page-head">
        <h1 tabIndex={-1}>{name}</h1>
        {page && mayBuild && (
          <div className="head-actions">
            <button className="plain" onClick={() => setDeleting(true)}>删除</button>
            <button className="primary" onClick={() => setUploading(true)}>上传新版本</button>
          </div>
        )}
      </div>
      {state.status === "error" && <p className="error">{state.error} {!state.missing && <button className="plain" onClick={reload}>重试</button>}</p>}
      {state.status === "loading" && !page && <p className="muted">加载中</p>}
      {page && (
        <>
          <p className="facts">
            <span>{page.rows} 行</span>
            <span>{page.columns.length} 列</span>
            <span>第 {page.version} 版</span>
            <span>{page.version === page.current_version ? `更新于 ${timeText(page.updated_at)}` : `这一版导入于 ${timeText(page.version_at)}`}</span>
            <span>来源 {originText(page.origin)}</span>
          </p>
          {page.version !== page.current_version && (
            <p className="viewing">正在看第 {page.version} 版，当前是第 {page.current_version} 版。 <a href={hrefFor({ page: "dataset", name, tab, version: null })}>回到当前版本</a></p>
          )}
          <nav className="tabs" aria-label="数据集的页面">
            {TABS.map((t) => (
              <a key={t} href={at(t)} aria-current={t === tab ? "page" : undefined} className={t === tab ? "active" : ""}>{TAB_LABEL[t]}</a>
            ))}
          </nav>
          {tab === "fields" && <Fields page={page} />}
          {tab === "preview" && <Preview page={page} name={name} />}
          {tab === "versions" && <Versions page={page} name={name} />}
        </>
      )}
      {deleting && <DeleteDialog name={name} page={page} onClose={() => setDeleting(false)} />}
      {uploading && <UploadDialog presetTarget={name} onClose={() => setUploading(false)} onDone={reload} />}
    </main>
  );
}

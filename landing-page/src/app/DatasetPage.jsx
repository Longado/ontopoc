import React, { useState } from "react";
import { csvHref, getDataset, getTypes } from "./api.js";
import { DeleteDialog } from "./DeleteDialog.jsx";
import { originLink, readerLinks } from "./datasetModel.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { isNumeric, keyText, percentText, timeText, typeLabel } from "./format.js";
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
                <td>{c.name}{c.fan && <span className="warn small block">{c.fan}</span>}</td>
                <td>{typeLabel(c.type)}</td>
                <td className="num" title={c.missing ? `缺 ${c.missing} 行` : undefined}>{percentText(c.fill_rate)}</td>
                <td className={c.key_check?.status === "failed" ? "bad" : c.possible_key || c.key_check || c.near_key ? "" : "muted"}>{keyText(c)}</td>
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
        <span className="muted">以 = + - @ 开头的文字，下载时前面会多一个 '</span>
      </div>
      <div className="table-wrap tall dense">
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

function Versions({ page, name, mayRead }) {
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
                <td className="keep">{mayRead && <a href={hrefFor({ page: "dataset", name, tab: "preview", version: r.current ? null : r.version })}>预览</a>}</td>
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
  const [types] = useLoad(getTypes, []);
  const page = state.data;
  const origin = originLink(page?.origin);
  const readers = readerLinks(page?.readers ?? [], Object.fromEntries((types.data ?? []).map((t) => [t.name, t.id])));
  const at =(t) => hrefFor({ page: "dataset", name, tab: t, version });
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: "数据" }, { label: "数据集", href: hrefFor({ page: "datasets" }) }, { label: name }]} title={name}
        sub={page && `${page.rows} 行，${page.columns.length} 列，第 ${page.version} 版`}
        actions={page && mayBuild && (
          <>
            <a className="button secondary" href={hrefFor({ page: "pipelinenew", dataset: name })}>用它建管道</a>
            <a className="button secondary" href={hrefFor({ page: "typenew", dataset: name })}>用它建对象类型</a>
            <button className="primary" onClick={() => setUploading(true)}>上传新版本</button>
          </>
        )}
        more={page && mayBuild ? [{ label: "删除数据集", onClick: () => setDeleting(true) }] : undefined} />
      {state.status === "error" && <p className="error">{state.error} {!state.missing && <button className="plain" onClick={reload}>重试</button>}</p>}
      {state.status === "loading" && !page && <p className="muted">加载中</p>}
      {page && (
        <>
          <dl className="ds-facts">
            <div><dt>更新</dt><dd>{page.version === page.current_version ? timeText(page.updated_at) : `这一版导入于 ${timeText(page.version_at)}`}</dd></div>
            <div>
              <dt>来源</dt>
              <dd>
                {origin.href && mayBuild ? <a href={origin.href}>{origin.label}</a> : origin.label}
                {origin.kind === "source" && <span className="muted">，拉取于 {timeText(page.version_at)}</span>}
              </dd>
            </div>
            <div>
              <dt>被用到</dt>
              <dd>
                {!readers.length ? <span className="muted">还没有对象类型或管道在用它</span> : readers.map((r, i) => (
                  <span key={`${r.kind}${r.name}`}>{i > 0 && "、"}<span className="muted">{r.kind} </span>{r.href ? <a href={r.href}>{r.name}</a> : r.name}</span>
                ))}
              </dd>
            </div>
            {page.versions.find((v) => v.version === page.version)?.source?.left_out?.length > 0 && <div><dt>没读的列</dt><dd className="warn">二进制列：{page.versions.find((v) => v.version === page.version).source.left_out.join("、")}</dd></div>}
          </dl>
          {page.version !== page.current_version && (
            <p className="viewing">正在看第 {page.version} 版，当前是第 {page.current_version} 版。 <a href={hrefFor({ page: "dataset", name, tab, version: null })}>回到当前版本</a></p>
          )}
          <nav className="tabs" aria-label="数据集的页面">
            {TABS.filter((t) => mayBuild || t !== "preview").map((t) => (   // a viewer reads no rows of a dataset: the preview and the download are for builders
              <a key={t} href={at(t)} aria-current={t === tab ? "page" : undefined} className={t === tab ? "active" : ""}>{TAB_LABEL[t]}</a>
            ))}
          </nav>
          {(tab === "fields" || (tab === "preview" && !mayBuild)) && <Fields page={page} />}
          {tab === "preview" && mayBuild && <Preview page={page} name={name} />}
          {tab === "versions" && <Versions page={page} name={name} mayRead={mayBuild} />}
        </>
      )}
      {deleting && <DeleteDialog name={name} page={page} onClose={() => setDeleting(false)} />}
      {uploading && <UploadDialog presetTarget={name} onClose={() => setUploading(false)} onDone={reload} />}
    </main>
  );
}

import React, { useState } from "react";
import { csvHref, getDataset, getTypes } from "./api.js";
import { DeleteDialog } from "./DeleteDialog.jsx";
import { originLink, readerLinks } from "./datasetModel.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { isNumeric, keyText, percentText, timeText, typeLabel } from "./format.js";
import { t, useT } from "./i18n/index.js";
import { Select } from "./Select.jsx";
import { TABS, TAB_LABEL, hrefFor } from "./routeModel.js";
import { readerKindLabel } from "./serverWords.js";
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
            <tr><th>{t("data.fields.column")}</th><th>{t("data.fields.type")}</th><th className="num">{t("data.fields.fill")}</th><th>{t("data.fields.keyCheck")}</th></tr>
          </thead>
          <tbody>
            {page.columns.map((c) => (
              <tr key={c.name}>
                <td className="strong">{c.name}{c.fan && <span className="warn small block">{c.fan}</span>}</td>
                <td className="muted">{typeLabel(c.type)}</td>
                <td className="num" title={c.missing ? t("data.fields.missing", { count: c.missing }) : undefined}>{percentText(c.fill_rate)}</td>
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
              {t("data.fields.multi", {
                columns: c.columns.join(" + "),
                result: c.status === "passed" ? t("data.fields.multiOk") : t("data.fields.multiBad", { dup: c.violations, blank: c.null_key_rows }),
                checked: c.rows_checked,
              })}
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
        <Select label={t("data.preview.version")} value={String(page.version)} onChange={(v) => { window.location.hash = hrefFor({ page: "dataset", name, tab: "preview", version: Number(v) === page.current_version ? null : Number(v) }); }}>
          {page.versions.map((v) => (
            <option key={v.version} value={v.version}>{t(v.current ? "data.preview.versionCurrent" : "data.preview.versionN", { n: v.version })}</option>
          ))}
        </Select>
        <span className="muted">
          {t("data.preview.range", { from: (preview.page - 1) * preview.limit + (preview.total ? 1 : 0), to: Math.min(preview.page * preview.limit, preview.total), total: preview.total })}
        </span>
        <a className="download" href={csvHref(name, page.version === page.current_version ? null : page.version)} download>{t("data.preview.download")}</a>
        <span className="muted small">{t("data.preview.csvNote")}</span>
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
        <nav className="pager" aria-label={t("data.preview.pagerAria")}>
          {preview.page > 1 ? <a href={at(preview.page - 1)}>{t("data.preview.prev")}</a> : <span className="faint">{t("data.preview.prev")}</span>}
          <span>{preview.page} / {preview.pages}</span>
          {preview.page < preview.pages ? <a href={at(preview.page + 1)}>{t("data.preview.next")}</a> : <span className="faint">{t("data.preview.next")}</span>}
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
          <tr><th>{t("data.versions.version")}</th><th>{t("data.versions.time")}</th><th>{t("data.versions.by")}</th><th>{t("data.versions.how")}</th><th>{t("data.versions.change")}</th><th></th></tr>
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
                <td className="strong">{t("data.versions.n", { n: r.version })}{r.current && <span className="here">{t("data.versions.current")}</span>}</td>
                <td>{timeText(r.at)}</td>
                <td className="keep">{r.who ?? <span className="faint">—</span>}</td>
                <td className="keep">{versionWay(r)}</td>
                <td>
                  {versionChangeText(r)}
                  {(r.changed_keys.length > 0 || r.added_keys.length > 0) && (
                    <details className="which">
                      <summary>{t("data.versions.which")}</summary>
                      {r.changed_keys.length > 0 && <p>{t("data.versions.changedRows", { keys: keyListText(r.changed_keys, r.changed) })}</p>}
                      {r.added_keys.length > 0 && <p>{t("data.versions.addedRows", { keys: keyListText(r.added_keys, r.added) })}</p>}
                    </details>
                  )}
                </td>
                <td className="keep">{mayRead && <a href={hrefFor({ page: "dataset", name, tab: "preview", version: r.current ? null : r.version })}>{t("data.versions.preview")}</a>}</td>
              </tr>
            ),
          )}
        </tbody>
      </table>
    </div>
  );
}

export function DatasetPage({ route }) {
  useT();
  const { name, tab, version, pageNo } = route;
  const [state, reload] = useLoad(() => getDataset(name, version, pageNo), [name, version, pageNo]);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const mayBuild = canBuild(useAuth().user);
  const [types] = useLoad(getTypes, []);
  const page = state.data;
  const origin = originLink(page?.origin);
  const readers = readerLinks(page?.readers ?? [], Object.fromEntries((types.data ?? []).map((ty) => [ty.name, ty.id])));
  const at = (to) => hrefFor({ page: "dataset", name, tab: to, version });
  const leftOut = page?.versions.find((v) => v.version === page.version)?.source?.left_out;
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("data.crumb.data") }, { label: t("data.list.title"), href: hrefFor({ page: "datasets" }) }, { label: name }]} title={name}
        sub={page && t("data.page.sub", { rows: t("data.n.rows", { count: page.rows }), columns: t("data.n.columns", { count: page.columns.length }), version: page.version })}
        actions={page && mayBuild && (
          <>
            <a className="button secondary" href={hrefFor({ page: "pipelinenew", dataset: name })}>{t("data.page.makePipeline")}</a>
            <a className="button secondary" href={hrefFor({ page: "typenew", dataset: name })}>{t("data.page.makeType")}</a>
            <button className="primary" onClick={() => setUploading(true)}>{t("data.page.newVersion")}</button>
          </>
        )}
        more={page && mayBuild ? [{ label: t("data.page.delete"), onClick: () => setDeleting(true) }] : undefined} />
      {state.status === "error" && <p className="error">{state.error} {!state.missing && <button className="plain" onClick={reload}>{t("common.retry")}</button>}</p>}
      {state.status === "loading" && !page && <p className="muted">{t("common.loading")}</p>}
      {page && (
        <>
          <dl className="ds-facts">
            <div><dt>{t("data.facts.updated")}</dt><dd>{page.version === page.current_version ? timeText(page.updated_at) : t("data.facts.importedThisVersion", { time: timeText(page.version_at) })}</dd></div>
            <div>
              <dt>{t("data.facts.source")}</dt>
              <dd>
                {origin.href && mayBuild ? <a href={origin.href}>{origin.label}</a> : origin.label}
                {origin.kind === "source" && <span className="muted">{t("data.facts.pulledAt", { time: timeText(page.version_at) })}</span>}
              </dd>
            </div>
            <div>
              <dt>{t("data.facts.usedBy")}</dt>
              <dd>
                {!readers.length ? <span className="muted">{t("data.facts.unused")}</span> : readers.map((r, i) => (
                  <span key={`${r.kind}${r.name}`}>{i > 0 && t("data.listSep")}<span className="muted">{readerKindLabel(r.kind)} </span>{r.href ? <a href={r.href}>{r.name}</a> : r.name}</span>
                ))}
              </dd>
            </div>
            {leftOut?.length > 0 && <div><dt>{t("data.facts.leftOut")}</dt><dd className="warn">{t("data.facts.binary", { cols: leftOut.join(t("data.listSep")) })}</dd></div>}
          </dl>
          {page.version !== page.current_version && (
            <p className="viewing">{t("data.page.viewing", { version: page.version, current: page.current_version })} <a href={hrefFor({ page: "dataset", name, tab, version: null })}>{t("data.page.backToCurrent")}</a></p>
          )}
          <nav className="tabs" aria-label={t("data.page.tabsAria")}>
            {TABS.filter((tb) => mayBuild || tb !== "preview").map((tb) => (   // a viewer reads no rows of a dataset: the preview and the download are for builders
              <a key={tb} href={at(tb)} aria-current={tb === tab ? "page" : undefined} className={tb === tab ? "active" : ""}>{TAB_LABEL[tb]}</a>
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

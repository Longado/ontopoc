import React, { useEffect, useState } from "react";
import { Explorer } from "./Explorer.jsx";
import { TypeActions } from "./TypeActions.jsx";
import { confirmConflictNote, confirmType, getTypeUses, getType, getTypeLog, noteConflict, proposeMeanings, setValuesHidden } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { timeText, typeLabel } from "./format.js";
import { ageText } from "./graphModel.js";
import { t } from "./i18n/index.js";
import { waitingText } from "./relationModel.js";
import { TYPE_TAB_LABEL, hrefFor } from "./routeModel.js";
import { statusOf } from "./statusModel.js";
import { State } from "./TypesPage.jsx";
import { TypeDerived } from "./TypeDerived.jsx";
import { TypeViews } from "./TypeViews.jsx";
import { alsoCalled, reportOnlyTag, conflictLine, conflictNoteLine, confirmersText, joinList, limitedNote, logText, meaningsSummary, offerFirstAction, otherNamesFrom, otherNamesText, reconfirmText, ruleExamples, ruleStanding, stateLine, tabCounts, typeSub, typeTabs, usesSummary } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { CiteText } from "./CiteText.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";

const TYPE_CRUMBS = (name) => [{ label: t("types.page.crumbGroup") }, { label: t("types.page.crumbTypes"), href: "#/types" }, { label: name }];

/** What stands behind a state, in one place: the line, who could confirm, and why it needs another look. */
function Standing({ item, noun }) {
  const line = stateLine(item, noun);
  return (
    <>
      {line && <p className="muted">{line}</p>}
      {waitingText(item) && <p className="warn">{waitingText(item)}</p>}
      {confirmersText(item) && <p className="muted small">{confirmersText(item)}</p>}
      {item.state === "needs_look" && item.reason && (
        <div className="reason">
          <strong>{t("types.page.whyLook")}</strong>
          <p>{item.reason}</p>
        </div>
      )}
    </>
  );
}

/** The meanings of one code column, as a section of their own: read as a table first; "Edit meanings" turns the meanings into inputs with Propose and Cancel. */
function Meanings({ type, prop, mayBuild, onChanged }) {
  const m = prop.meanings;
  const saved = Object.fromEntries(m.values.map((v) => [v.value, v.label]));
  const savedOthers = Object.fromEntries(m.values.map((v) => [v.value, otherNamesText(v.other_names)]));
  const [draft, setDraft] = useState(saved);
  const [others, setOthers] = useState(savedOthers);   // the other names of each meaning, as the text of its box
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const changed = m.values.some((v) => (draft[v.value] ?? "") !== v.label || otherNamesText(otherNamesFrom(others[v.value])) !== savedOthers[v.value]);
  const act = async (run) => {
    setBusy(true);
    setError("");
    try {
      await run();
      onChanged();
    } catch (e) {
      setError(e.message);
    }
    setBusy(false);
  };
  const propose = () => act(() => proposeMeanings(type.id, prop.column, m.values.map((v) => ({ value: v.value, label: draft[v.value] ?? "", other_names: otherNamesFrom(others[v.value]) }))));
  const confirm = () => act(() => confirmType(type.id, m.version, m.seen, prop.column));
  const cancel = () => {
    setDraft(saved);
    setOthers(savedOthers);
    setEditing(false);
  };
  const hasThen = m.state === "needs_look";   // what the rows were when it was confirmed matters only once the data has moved
  const editable = mayBuild && editing;
  return (
    <section className="meanings" aria-label={t("types.meanings.aria", { name: prop.name })}>
      <div className="section-head">
        <h2 className="section">{t("types.meanings.title", { name: prop.name })} <State item={m} /></h2>
        <span className="muted small">{meaningsSummary(m)}</span>
        {mayBuild && !editing && <button className="secondary" onClick={() => setEditing(true)}>{t("types.meanings.edit")}</button>}
      </div>
      <Standing item={m} noun={t("types.meanings.noun")} />
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>{t("types.meanings.value")}</th><th>{t("types.meanings.meaning")}</th>{editable && <th>{t("types.form.meaningOthers")}</th>}{hasThen && !m.limited_note && <th className="num">{t("types.meanings.thenRows")}</th>}{!m.limited_note && <th className="num">{t("types.meanings.nowRows")}</th>}</tr>
          </thead>
          <tbody>
            {m.values.map((v) => (
              <tr key={v.value}>
                <td>{v.value}</td>
                <td>
                  {editable ? (
                    <input type="text" aria-label={t("types.meanings.inputAria", { column: prop.column, value: v.value })} value={draft[v.value] ?? ""} placeholder={v.in_data ? t("types.meanings.placeholder") : t("types.meanings.gone")}
                      onChange={(e) => setDraft({ ...draft, [v.value]: e.target.value })} />
                  ) : (v.label ? <>{v.label}{alsoCalled(v.other_names) && <span className="muted small block">{alsoCalled(v.other_names)}</span>}</> : <span className="faint">{t("types.meanings.unconfirmed")}</span>)}
                </td>
                {editable && (
                  <td><input type="text" aria-label={t("types.form.meaningOthersAria", { column: prop.column, value: v.value })} value={others[v.value] ?? ""} placeholder={t("types.otherNamesPlaceholder")}
                    onChange={(e) => setOthers({ ...others, [v.value]: e.target.value })} /></td>
                )}
                {hasThen && !m.limited_note && <td className="num">{v.rows_at_confirmation ?? <span className="faint">—</span>}</td>}
                {!m.limited_note && <td className="num">{v.rows ?? <span className="faint">{t("types.none")}</span>}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {m.limited_note && <p className="muted small">{m.limited_note}</p>}
      {mayBuild && (
        <div className="inline">
          {editing && <button className="primary" onClick={propose} disabled={busy || !changed}>{t("types.meanings.propose")}</button>}
          {editing && <button className="plain" onClick={cancel} disabled={busy}>{t("common.cancel")}</button>}
          {editing && !changed && <span className="muted small">{t("types.meanings.changeToPropose")}</span>}
          {!editing && m.state === "needs_look" && <button className="secondary" onClick={propose} disabled={busy}>{t("types.meanings.propose")}</button>}
          {!editing && m.can_confirm && !changed && <button className="primary" onClick={confirm} disabled={busy}>{t("types.meanings.confirm")}</button>}
          {(editing || m.state === "needs_look") && <span className="muted small">{t("types.meanings.needsSecond")}</span>}
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}

/** The value rules this person may read: what each says, how many rows break it now (of their own rows, when a row rule limits them) and a few of their keys. */
function Rules({ type }) {
  const broken = type.rules.some((r) => r.broken && !r.report_only);   // a rule that only reports does not stop confirming
  return (
    <section className="rules" aria-label={t("types.rules.title")}>
      <h2 className="section">{t("types.rules.title")}</h2>
      <ul className="readers">
        {type.rules.map((r, i) => (
          <li key={i}>
            <span className={r.broken ? "warn" : undefined}>{t("types.rules.line", { says: r.says, standing: ruleStanding(r, type.rows_limited) })}</span>
            {r.examples?.length > 0 && <span className="muted small block">{t("types.rules.examples", { keys: ruleExamples(r) })}</span>}
            {r.report_only && <span className="muted small block">{reportOnlyTag(r)}</span>}
            {r.cite && <CiteText cite={r.cite} className="small block" />}
          </li>
        ))}
      </ul>
      {broken && type.state !== "confirmed" && <p className="warn">{t("types.rules.blocks")}</p>}
      {type.rules_note && <p className="muted small">{type.rules_note}</p>}
    </section>
  );
}

/** Two rules that disagree: both rules with what each cites, how many rows meet both conditions now, and the "known: asked <who>" note, which a builder writes and
 * another confirms. Listed until a rule changes or the note is confirmed; it does not stop confirming the type. */
function Conflicts({ type, mayBuild, reload }) {
  const [asked, setAsked] = useState({});
  const [error, setError] = useState("");
  const act = async (run) => {
    setError("");
    try {
      await run();
      setAsked({});
      reload();
    } catch (e) {
      setError(e.message);
    }
  };
  return (
    <section className="rules" aria-label={t("types.conflicts.title")}>
      <h2 className="section">{t("types.conflicts.title")}</h2>
      <p className="muted small">{t("types.conflicts.hint")}</p>
      <ul className="readers">
        {type.conflicts.map((c) => (
          <li key={c.key}>
            <span className="warn">{conflictLine(c)}</span>
            {c.rules.map((r) => (
              <span key={r.index} className="small block">{r.says}{r.cite && <> — <CiteText cite={r.cite} /></>}</span>
            ))}
            {c.note && <span className="muted small block">{conflictNoteLine(c.note)}</span>}
            {mayBuild && c.note?.may_confirm && <button className="primary" onClick={() => act(() => confirmConflictNote(type.id, c.key))}>{t("types.conflicts.confirm")}</button>}
            {mayBuild && c.note && !c.note.may_confirm && c.note.held && <span className="muted small block">{c.note.held}</span>}
            {mayBuild && !c.note && (
              <span className="inline">
                <input type="text" maxLength={80} aria-label={t("types.conflicts.askedAria")} placeholder={t("types.conflicts.askedPlaceholder")} value={asked[c.key] ?? ""}
                  onChange={(e) => setAsked({ ...asked, [c.key]: e.target.value })} />
                <button className="secondary" disabled={!(asked[c.key] ?? "").trim()} onClick={() => act(() => noteConflict(type.id, c.key, asked[c.key].trim()))}>{t("types.conflicts.record")}</button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {error && <p className="error">{error}</p>}
    </section>
  );
}

function Properties({ type, mayBuild, reload }) {
  const QA_HELP = t("types.props.qaHelp");
  const [error, setError] = useState("");
  const allow = async (column, on) => {
    setError("");
    try {
      await setValuesHidden(type.id, column, !on);   // the box says what is allowed; the service keeps what is hidden
      reload();
    } catch (e) {
      setError(e.message);
    }
  };
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>{t("types.props.name")}</th><th>{t("types.props.column")}</th><th>{t("types.props.type")}</th><th>{t("types.props.key")}</th>
              {mayBuild && <th>{t("types.props.allow")} <span className="help" tabIndex={0} role="img" aria-label={QA_HELP} title={QA_HELP}>?</span></th>}
            </tr>
          </thead>
          <tbody>
            {type.properties.map((p) => (
              <tr key={p.column}>
                <td>{p.name}{alsoCalled(p.other_names) && <span className="muted small block">{alsoCalled(p.other_names)}</span>}{p.fan && <span className="warn small block">{p.fan}</span>}</td>
                <td className="muted">{p.column}</td>
                <td>{p.enum ? <>{t("types.props.code", { type: typeLabel(p.type) })} {p.meanings.state ? <State item={p.meanings} /> : <span className="muted small">{t("types.props.meaningsUnwritten")}</span>}</> : typeLabel(p.type)}</td>
                <td>{p.key ? t("types.yes") : ""}</td>
                {mayBuild && (
                  <td>
                    {p.key ? <span className="faint">{t("types.props.keyNotSent")}</span> : (
                      <label className="check">
                        <input type="checkbox" checked={!p.hide_values} onChange={(e) => allow(p.column, e.target.checked)} aria-label={t("types.props.allowAria", { name: p.name })} />
                        {p.hide_values ? t("types.props.hidden") : t("types.props.sendable")}
                      </label>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {error && <p className="error">{error}</p>}
      {type.rules?.length > 0 && <Rules type={type} />}
      {type.conflicts?.length > 0 && <Conflicts type={type} mayBuild={mayBuild} reload={reload} />}
      {type.properties.filter((p) => p.enum).map((p) => (
        <Meanings key={`${p.column}-${p.meanings.version ?? 0}-${p.meanings.state}`} type={type} prop={p} mayBuild={mayBuild} onChanged={reload} />
      ))}
    </>
  );
}

function Log({ id }) {
  const [state] = useLoad(() => getTypeLog(id), [id]);
  if (state.status === "error") return <p className="error">{state.error}</p>;
  if (!state.data) return <p className="muted">{t("common.loading")}</p>;
  return (
    <div className="table-wrap">
      <table className="log">
        <thead><tr><th>{t("types.log.when")}</th><th>{t("types.log.who")}</th><th>{t("types.log.what")}</th></tr></thead>
        <tbody>
          {state.data.map((e, i) => {
            const line = logText(e);
            return <tr key={i}><td className="keep">{timeText(e.at)}</td><td className="keep">{line.who}</td><td>{line.text}</td></tr>;
          })}
        </tbody>
      </table>
    </div>
  );
}

const USE_HREF = {
  views: (id) => hrefFor({ page: "type", id, tab: "views" }),
  derived: (id) => hrefFor({ page: "type", id, tab: "derived" }),
  actions: (id) => hrefFor({ page: "type", id, tab: "actions" }),
  relations: (_id, item) => hrefFor({ page: "relation", id: item.id }),
  answers: (_id, item) => hrefFor({ page: "qa", id: item.id }),
};

/** Used by: one line with a count for each kind; it opens to the names. Kinds nothing uses are not listed. */
function Uses({ id, uses }) {
  if (!uses?.used_by.length) return null;
  return (
    <details className="uses">
      <summary><span className="muted">{t("types.page.usedBy")}</span> {usesSummary(uses)}</summary>
      <dl className="defs">
        {uses.used_by.map((u) => (
          <React.Fragment key={u.kind}>
            <dt>{u.label} {u.count}</dt>
            <dd>{u.items.map((item, i) => <span key={item.id}>{i > 0 && t("types.sep")}<a href={USE_HREF[u.kind](id, item)}>{item.name}</a>{item.state && item.state !== "confirmed" && <span className="muted small"> {statusOf(item.state).label}</span>}</span>)}</dd>
          </React.Fragment>
        ))}
      </dl>
    </details>
  );
}

export function TypePage({ route }) {
  const { id, tab } = route;
  const [state, reload] = useLoad(() => getType(id), [id]);
  const [uses] = useLoad(() => (state.data?.waiting ? Promise.resolve(null) : getTypeUses(id)), [id, state.data?.version, state.data?.waiting]);   // a waiting type has no uses to show
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionCount, setActionCount] = useState(null);   // the 行为 list's own count, once it is read
  useEffect(() => setActionCount(null), [id]);
  const mayBuild = canBuild(useAuth().user);
  const ty = state.data;
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmType(id, ty.version, ty.seen);
      reload();
    } catch (e) {
      setError(e.message);
      if (e.code === 409) reload();   // what was read has moved: show what is there now
    }
    setBusy(false);
  };
  const uploaded = uses.data?.data.uploaded_at ? `${ageText(uses.data.data.uploaded_at)}${uses.data.data.who ? `${t("types.comma")}${uses.data.data.who}` : ""}` : "";
  const counts = ty && !ty.waiting ? tabCounts(ty, uses.data, actionCount == null ? {} : { actions: actionCount }) : {};
  return (
    <main className="page">
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !ty && <p className="muted">{t("common.loading")}</p>}
      {ty?.waiting && (
        <>
          <PageHeader crumbs={TYPE_CRUMBS(ty.name)} title={ty.name} status={<State item={ty} />} />
          <p className="warn">{reconfirmText(ty.waiting_for)}</p>
          <p className="muted">{t("types.page.waitingNote")}</p>
        </>
      )}
      {ty && !ty.waiting && (
        <>
          <PageHeader crumbs={TYPE_CRUMBS(ty.name)} title={ty.name} status={<State item={ty} />} sub={typeSub(ty, uploaded)}
            actions={mayBuild && (
              <>
                {!ty.columns_kept && <a className="button secondary" href={hrefFor({ page: "typeedit", id })}>{t("types.page.edit")}</a>}
                {ty.can_confirm && <button className="primary" onClick={confirm} disabled={busy}>{t("types.page.confirm")}</button>}
              </>
            )} />
          {error && <p className="error">{error}</p>}
          <div className="type-notes">
            {alsoCalled(ty.other_names) && <p className="muted">{alsoCalled(ty.other_names)}</p>}
            {ty.description && <p>{ty.description}</p>}
            {ty.columns_kept > 0 && <p className="faint small">{t("types.page.keptColumns", { count: ty.columns_kept })}</p>}
            {ty.visible_to && ty.visible_to !== "everyone" && <p className="muted small">{t("types.page.visibleOnly", { who: ty.visible_to.length ? joinList(ty.visible_to) : t("types.admins") })}</p>}
            {!ty.rows_limited && !ty.columns_kept && <p className="small"><a href={hrefFor({ page: "dataset", name: ty.dataset, tab: "fields" })}>{t("types.page.sourceLink", { dataset: ty.dataset })}</a></p>}
            {limitedNote(ty) && <p className="muted small">{limitedNote(ty)}</p>}
            <Standing item={ty} noun={t("types.page.noun")} />
            <Uses id={id} uses={uses.data} />
          </div>
          <nav className="tabs" aria-label={t("types.page.tabsAria")}>
            {typeTabs(counts, tab, mayBuild).map((k) => (
              <a key={k} href={hrefFor({ page: "type", id, tab: k })} aria-current={k === tab ? "page" : undefined} className={k === tab ? "active" : ""}>
                {TYPE_TAB_LABEL[k]}{counts[k] != null && <span className="tab-count">{counts[k]}</span>}
              </a>
            ))}
            {offerFirstAction(counts, tab, mayBuild) && <a className="muted" href={hrefFor({ page: "type", id, tab: "actions" })} title={t("types.page.addActionTitle")}>{t("types.page.addAction")}</a>}
          </nav>
          {tab === "props" && <Properties type={ty} mayBuild={mayBuild} reload={reload} />}
          {tab === "derived" && <TypeDerived type={ty} mayBuild={mayBuild} />}
          {tab === "views" && <TypeViews type={ty} mayBuild={mayBuild} />}
          {tab === "actions" && mayBuild && <TypeActions type={ty} mayBuild={mayBuild} onCount={setActionCount} />}
          {tab === "objects" && <Explorer key={`${id}|${route.q ?? ""}`} id={id} route={route} />}
          {tab === "log" && <Log id={id} />}
        </>
      )}
    </main>
  );
}

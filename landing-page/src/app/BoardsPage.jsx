import React, { useEffect, useId, useRef, useState } from "react";
import { ChartResult, Standing } from "./ChartView.jsx";
import { deleteBoard, getBoard, getBoardData, getBoards } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { controlsOf, expiryText, headlineStands, paramValues, refreshText, scopeLabel, scopeText, shareLink, unavailableText } from "./boardModel.js";
import { useT } from "./i18n/index.js";
import { Answer, Basis } from "./QaPage.jsx";
import { queryRecord } from "./qaModel.js";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";
import { Icon } from "./ui/Icon.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";
import "./boards-home.css";
import { EmptyState } from "./ui/EmptyState.jsx";

/** The view a result was worked out on, by name, when its caliber names one. */
const viewOf = (result) => result.standing?.lines?.find((l) => l.kind === "view")?.name ?? "";

/** "Show basis": the full evidence (the caliber, one line for each definition) kept behind a button, quiet until asked for. */
function BasisToggle({ children }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="bh-basis">
      <button type="button" className="bh-basis-btn" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <Icon name={open ? "chevron-down" : "chevron-right"} size={12} />{open ? t("boards.card.hideBasis") : t("boards.card.showBasis")}
      </button>
      <div id={id} className="bh-basis-body" hidden={!open}>{children}</div>
    </div>
  );
}

/** One short line under a number or chart: "107 rows · Valid orders view", plus the confirmed (or not) chip. */
function CardMeta({ result }) {
  const t = useT();
  const view = viewOf(result);
  const confirmed = result.standing.confirmed;
  const count = typeof result.rows === "number" ? result.rows : typeof result.total === "number" ? result.total : null;   // a rows card carries the rows themselves in result.rows
  return (
    <div className="bh-meta">
      <span className="bh-meta-line">{[count === null ? "" : t("boards.card.rows", { count }), view && t("boards.card.viewName", { name: view })].filter(Boolean).join(" · ")}</span>
      <span className={`bh-chip ${confirmed ? "bh-chip-ok" : "bh-chip-grey"}`}>{confirmed ? <Icon name="check" size={11} /> : null}{confirmed ? t("boards.card.confirmed") : t("boards.card.notConfirmed")}</span>
    </div>
  );
}

/** The board's note on who can open a shared link: an info button; hover, focus or a tap shows the full sentence. */
function SignInNote({ note }) {
  const [open, setOpen] = useState(false);
  return (
    <button type="button" className={`bh-info${open ? " open" : ""}`} aria-label={note} onClick={() => setOpen(!open)} onBlur={() => setOpen(false)}>
      <Icon name="info" size={14} /><span className="bh-info-text">{note}</span>
    </button>
  );
}

function BasisLines({ result }) {
  const t = useT();
  // only the definition lines: the reason a result is grey is shown on the card itself, above the disclosure
  return result.standing.lines.length ? (
    <div className="standing">
      <ul className="caliber">{result.standing.lines.map((l) => <li key={l.id} className={l.confirmed ? "" : "grey"}>{l.line}</li>)}</ul>
    </div>
  ) : (
    <div className="standing">
      <p className="muted small">{t("boards.card.caliber")}{result.query.filters.length ? t("boards.card.extra", { count: result.query.filters.length }) : ""}</p>
    </div>
  );
}

/** The components of a board as cards: title (small, muted), the number or chart (grey with the reason when what it stands on is not confirmed), one short line, and the caliber behind "Show basis". */
export function BoardCards({ data }) {
  const t = useT();
  return (
    <div className="board-grid">
      {data.components.map((c) => (
        <section key={c.id} className={`board-card kind-${c.chart?.kind}`}>
          <h2 className="item-title">{c.title}</h2>
          {c.status === "waiting" ? (
            <>
              <p className="muted">{unavailableText(c)}</p>
              {c.last ? (
                <div className="last-confirmed">
                  <p className="muted small">{t("boards.card.lastConfirmed", { when: timeText(c.last.at) })}</p>
                  <ChartResult result={c.last.result} withStanding={false} bare />
                  <CardMeta result={c.last.result} />
                  {c.last.result.standing.lines.length > 0 && <BasisToggle><Standing standing={c.last.result.standing} /></BasisToggle>}
                </div>
              ) : <p className="muted small">{t("boards.card.noneConfirmed")}</p>}
            </>
          ) : c.status !== "ok" ? <p className="muted">{unavailableText(c)}</p> : c.chart?.kind === "query" ? (
            <>
              <Answer record={queryRecord(c.result)} />
              <Basis record={queryRecord({ ...c.result, query_text: c.result.text })} />
            </>
          ) : (
            <>
              <ChartResult result={c.result} withStanding={false} bare />
              <CardMeta result={c.result} />
              {!c.result.standing.confirmed && <Standing standing={{ ...c.result.standing, lines: [] }} />}
              <BasisToggle><BasisLines result={c.result} /></BasisToggle>
            </>
          )}
        </section>
      ))}
    </div>
  );
}

function BarPicks({ bar, picked, setPicked }) {
  const t = useT();
  if (!bar.length) return null;
  return (
    <div className="inline wide board-bar" role="group" aria-label={t("boards.bar.aria")}>
      {bar.map((f) => (
        <label key={f.field} className="field">
          <span className="caption">{f.label}</span>
          {f.options ? (
            <Select label={f.label} value={picked[f.field] ?? ""} onChange={(v) => setPicked({ ...picked, [f.field]: v })}>
              <option value="">{t("boards.bar.all")}</option>
              {f.options.map((o) => <option key={o.value} value={o.value}>{o.label ? `${o.value} ${o.label}` : o.value}</option>)}
            </Select>
          ) : <input type="text" aria-label={f.label} value={picked[f.field] ?? ""} onChange={(e) => setPicked({ ...picked, [f.field]: e.target.value })} />}
        </label>
      ))}
    </div>
  );
}

/** The board's parameters: typed once at the top, sent to every query card when the reader presses Enter or leaves the box; empty is the default. */
function ParamInputs({ params, typed, setTyped }) {
  const t = useT();
  const [draft, setDraft] = useState(typed);
  if (!params?.length) return null;
  const apply = () => setTyped(paramValues(params, draft));
  return (
    <form className="inline wide board-bar" role="group" aria-label={t("boards.params.aria")} onSubmit={(e) => { e.preventDefault(); apply(); }}>
      {params.map((p) => (
        <label key={p.name} className="field">
          <span className="caption">{p.label}</span>
          <input type="text" aria-label={p.label} placeholder={p.default} value={draft[p.name] ?? ""} onChange={(e) => setDraft({ ...draft, [p.name]: e.target.value })} onBlur={apply} />
        </label>
      ))}
      <button className="secondary" type="submit">{t("boards.params.apply")}</button>
    </form>
  );
}

export function BoardPage({ route }) {
  const t = useT();
  const { id } = route;
  const { user } = useAuth();
  const [picked, setPicked] = useState({});
  const [typed, setTyped] = useState({});
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [board] = useLoad(() => getBoard(id), [id]);
  const [data, reload] = useLoad(() => getBoardData(id, picked, typed), [id, JSON.stringify(picked), JSON.stringify(typed)]);
  const last = useRef();
  if (data.data) last.current = { id, data: data.data };
  const controls = controlsOf(data.data, last.current, id);   // the filter bar stays while a pick loads or fails, so the pick can be changed back
  const seconds = board.data?.refresh_seconds ?? 0;
  useEffect(() => {
    if (!seconds) return undefined;
    const timer = setInterval(reload, seconds * 1000);   // the same request again: the figures stay on screen until the new ones arrive
    return () => clearInterval(timer);
  }, [seconds]);
  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);
  const b = board.data;
  const remove = async () => {
    if (!window.confirm(t("boards.page.confirmDelete", { name: b.name }))) return;
    try {
      await deleteBoard(id);
      window.location.hash = "#/boards";
    } catch (e) {
      setError(e.message);
    }
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(shareLink(window.location.origin, id));
      setCopied(true);
      setError("");
    } catch {
      setCopied(false);
      setError(t("boards.page.copyFailed"));
    }
  };
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("boards.title"), href: "#/boards" }, { label: b?.name ?? "…" }]} title={b?.name ?? t("boards.title")}
        actions={b && (
          <>
            <button className="secondary" onClick={copy}>{copied ? t("boards.page.copied") : t("boards.page.copy")}</button>
            <button className="secondary" onClick={reload}>{t("boards.page.refresh")}</button>
            {b.may_change && canBuild(user) && <a className="button secondary" href={`#/boards/${id}/edit`}>{t("boards.page.edit")}</a>}
            {b.may_change && canBuild(user) && <button className="plain" onClick={remove}>{t("boards.page.delete")}</button>}
          </>
        )} />
      {board.status === "error" && <p className="error">{board.error}</p>}
      {b && (
        <>
          <p className="bh-facts">
            <span className="bh-chip">{t("boards.page.owner", { owner: b.owner })}</span>
            <span className="bh-chip">{t("boards.page.publishedTo", { scope: scopeText(b) })}</span>
            <span className="bh-chip">{expiryText(b)}</span>
            <span className="bh-chip">{refreshText(b.refresh_seconds)}</span>
            {b.sign_in_note && <SignInNote note={b.sign_in_note} />}
          </p>
          {error && <p className="error">{error}</p>}
        </>
      )}
      {board.status !== "error" && data.status === "error" && <p className="error" role="alert">{data.error}</p>}
      {controls && (
        <>
          {data.data && <p className={headlineStands(data.data.headline) ? "grey-banner" : "muted small"}>{data.data.headline.text}</p>}
          <BarPicks bar={controls.bar} picked={picked} setPicked={setPicked} />
          <ParamInputs params={controls.params} typed={typed} setTyped={setTyped} />
          {data.data && <BoardCards data={data.data} />}
          {data.data && <p className="muted small">{t("boards.page.readAt", { when: timeText(data.data.read_at) })}</p>}
        </>
      )}
      {!data.data && data.status === "loading" && <p className="muted">{t("boards.loading")}</p>}
    </main>
  );
}

export function BoardsPage() {
  const t = useT();
  const { user } = useAuth();
  const [state, reload] = useLoad(() => getBoards(), []);
  const boards = state.data?.dashboards ?? [];
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("boards.title") }]} title={t("boards.title")} sub={t("boards.sub")}
        actions={canBuild(user) && <a className="button primary" href="#/boards/new">{t("boards.new")}</a>} />
      {state.status === "error" && <p className="error">{state.error} <button className="plain" onClick={reload}>{t("common.retry")}</button></p>}
      {state.data && boards.length === 0 && (canBuild(user)
        ? <EmptyState icon="board" title={t("boards.empty.title")} text={t("boards.empty.builder")} action={{ label: t("boards.new"), href: "#/boards/new" }} />
        : <EmptyState icon="board" title={t("boards.empty.title")} text={t("boards.empty.viewer")} action={{ label: t("boards.empty.ask"), href: "#/qa" }} />)}
      {boards.length > 0 && (
        <ul className="bh-list">
          {boards.map((b) => (
            <li key={b.id}>
              <a className="bh-board" href={`#/boards/${b.id}`}>
                <span className="bh-board-top"><span className="bh-board-name">{b.name}</span><Icon name="chevron-right" size={14} /></span>
                <span className="bh-board-sub">{t("boards.list.components", { count: b.components })} · {t("boards.list.updated", { when: timeText(b.updated_at) })}</span>
                <span className="bh-facts">
                  <span className="bh-chip">{b.owner}{b.mine ? ` · ${t("boards.col.me")}` : ""}</span>
                  <span className="bh-chip">{scopeLabel(b.scope)}</span>
                  <span className="bh-chip">{expiryText(b)}</span>
                </span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

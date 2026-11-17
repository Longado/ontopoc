import React, { useEffect, useState } from "react";
import { ChartResult, Standing } from "./ChartView.jsx";
import { deleteBoard, getBoard, getBoardData, getBoards } from "./api.js";
import { useAuth } from "./Auth.jsx";
import { canBuild } from "./authModel.js";
import { expiryText, headlineStands, paramValues, refreshText, scopeLabel, scopeText, shareLink, unavailableText } from "./boardModel.js";
import { useT } from "./i18n/index.js";
import { Answer, Basis } from "./QaPage.jsx";
import { queryRecord } from "./qaModel.js";
import { timeText } from "./format.js";
import { Select } from "./Select.jsx";
import { useLoad } from "./useLoad.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { EmptyState } from "./ui/EmptyState.jsx";

/** The components of a board as cards: each with its title, its number or chart (grey with the reason when what it stands on is not confirmed) and its caliber. */
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
                  <ChartResult result={c.last.result} withStanding={false} />
                  {c.last.result.standing.lines.length > 0 && <Standing standing={c.last.result.standing} />}
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
              <ChartResult result={c.result} withStanding={false} />
              {c.result.standing.lines.length ? <Standing standing={c.result.standing} /> : (
                <div className="standing">
                  <p className="muted small">{t("boards.card.caliber")}{c.result.query.filters.length ? t("boards.card.extra", { count: c.result.query.filters.length }) : ""}</p>
                  {!c.result.standing.confirmed && <Standing standing={{ ...c.result.standing, lines: [] }} />}
                </div>
              )}
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
  const [tick, setTick] = useState(0);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [board] = useLoad(() => getBoard(id), [id]);
  const [data] = useLoad(() => getBoardData(id, picked, typed), [id, JSON.stringify(picked), JSON.stringify(typed), tick]);
  const seconds = board.data?.refresh_seconds ?? 0;
  useEffect(() => {
    if (!seconds) return undefined;
    const timer = setInterval(() => setTick((n) => n + 1), seconds * 1000);
    return () => clearInterval(timer);
  }, [seconds]);
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
    } catch {
      setError(t("boards.page.copyFailed"));
    }
  };
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("boards.title"), href: "#/boards" }, { label: b?.name ?? "…" }]} title={b?.name ?? t("boards.title")}
        actions={b && (
          <>
            <button className="secondary" onClick={copy}>{copied ? t("boards.page.copied") : t("boards.page.copy")}</button>
            <button className="secondary" onClick={() => setTick((n) => n + 1)}>{t("boards.page.refresh")}</button>
            {b.may_change && canBuild(user) && <a className="button secondary" href={`#/boards/${id}/edit`}>{t("boards.page.edit")}</a>}
            {b.may_change && canBuild(user) && <button className="plain" onClick={remove}>{t("boards.page.delete")}</button>}
          </>
        )} />
      {board.status === "error" && <p className="error">{board.error}</p>}
      {b && (
        <>
          <p className="facts">
            <span>{t("boards.page.owner", { owner: b.owner })}</span>
            <span>{t("boards.page.publishedTo", { scope: scopeText(b) })}</span>
            <span>{expiryText(b)}</span>
            <span>{refreshText(b.refresh_seconds)}</span>
          </p>
          <p className="muted small">{b.sign_in_note}</p>
          {error && <p className="error">{error}</p>}
        </>
      )}
      {data.status === "error" && <p className="error">{data.error}</p>}
      {data.data && (
        <>
          <p className={headlineStands(data.data.headline) ? "grey-banner" : "muted small"}>{data.data.headline.text}</p>
          <BarPicks bar={data.data.bar} picked={picked} setPicked={setPicked} />
          <ParamInputs params={data.data.params} typed={typed} setTyped={setTyped} />
          <BoardCards data={data.data} />
          <p className="muted small">{t("boards.page.readAt", { when: timeText(data.data.read_at) })}</p>
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
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("boards.col.name")}</th><th>{t("boards.col.owner")}</th><th>{t("boards.col.scope")}</th><th>{t("boards.col.expiry")}</th><th className="num">{t("boards.col.components")}</th><th>{t("boards.col.updated")}</th></tr></thead>
            <tbody>
              {boards.map((b) => (
                <tr key={b.id}>
                  <td><a href={`#/boards/${b.id}`}>{b.name}</a></td>
                  <td>{b.owner}{b.mine && <span className="chip chip-blue">{t("boards.col.me")}</span>}</td>
                  <td>{scopeLabel(b.scope)}</td>
                  <td>{expiryText(b)}</td>
                  <td className="num">{b.components}</td>
                  <td>{timeText(b.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

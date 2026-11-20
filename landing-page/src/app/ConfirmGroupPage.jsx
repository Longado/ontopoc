import React, { useState } from "react";
import { confirmGroup, getQueueGroup, previewImpact } from "./api.js";
import { ImpactList, ReceiptPanel } from "./ImpactList.jsx";
import { receiptElements } from "./impactModel.js";
import { KIND, groupTitle, markKey, missing, requestItems, resultLines, withMark } from "./batchModel.js";
import { timeText } from "./format.js";
import { t } from "./i18n/index.js";
import { itemHref } from "./relationModel.js";
import { State } from "./TypesPage.jsx";
import { stateLine } from "./typeModel.js";
import { useLoad } from "./useLoad.js";
import { sortByProblem } from "./confirmModel.js";
import { PageHeader } from "./ui/PageHeader.jsx";
import { newValueText } from "./viewModel.js";

/** What each value of a set of meanings meant and how many rows had it when it was last confirmed, beside what it says and has now. */
function Values({ values }) {
  return (
    <div className="table-wrap">
      <table className="wraps">
        <thead>
          <tr><th>{t("review.values.value")}</th><th>{t("review.values.then")}</th><th className="num">{t("review.values.rows")}</th><th>{t("review.values.now")}</th><th className="num">{t("review.values.rows")}</th></tr>
        </thead>
        <tbody>
          {values.map((v) => (
            <tr key={v.value} className={(v.label_then ?? "") !== v.label || v.rows_then !== v.rows ? "changed" : ""}>
              <td>{v.value}</td>
              <td className="muted">{v.label_then ?? <span className="faint">{t("types.none")}</span>}</td>
              <td className="num muted">{v.rows_then ?? <span className="faint">—</span>}</td>
              <td>{v.label || <span className="faint">{t("review.values.noMeaning")}</span>}</td>
              <td className="num">{v.rows ?? <span className="faint">{t("types.none")}</span>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Item({ item, marks, onMark, picked, onPick }) {
  return (
    <section className="card confirm-step">
      <div className="page-head">
        <h2 className="item-title">{KIND[item.kind]} <a href={itemHref(item)}>{item.title}</a></h2>
        <State item={item} />
      </div>
      <p className="muted small">{stateLine(item, t("review.item.noun")) || t("review.item.fallback")}</p>
      <ul className="checks">
        {item.lines.filter((l) => !item.values || !l.ok).map((l, i) => <li key={i} className={l.ok ? "" : l.strong ? "warn strong" : "warn"}>{l.text}</li>)}
      </ul>
      {item.values && <Values values={item.values} />}
      {item.ready && item.new_values?.map((v) => {
        const key = `${v.column}|${v.value}`;
        return (
          <fieldset key={key} className="new-value">
            <legend>{newValueText(v)}</legend>
            <label><input type="radio" name={`new-${item.element}-${key}`} checked={picked[key] === "in"} onChange={() => onPick(item.element, key, "in")} /> {t("types.view.include")}</label>
            <label><input type="radio" name={`new-${item.element}-${key}`} checked={picked[key] === "out"} onChange={() => onPick(item.element, key, "out")} /> {t("types.view.exclude")}</label>
          </fieldset>
        );
      })}
      {item.ready
        ? <label className="check"><input type="checkbox" checked={marks.includes(markKey(item))} onChange={(e) => onMark(item, e.target.checked)} /> {t("review.item.seen")}</label>
        : <p className="warn">{t("review.item.notConfirmed", { why: item.why_not })}</p>}
    </section>
  );
}

function Done({ result }) {
  const [receipt, setReceipt] = useState(true);
  return (
    <div className="cards">
      {receipt && result.confirmed.length > 0 && <ReceiptPanel elements={receiptElements(result)} onClose={() => setReceipt(false)} />}
      <section className="card">
        <ul className="checks">
          {resultLines(result).map((line, i) => <li key={i}>{line}</li>)}
        </ul>
        {result.hidden > 0 && <p className="muted">{t("review.done.hidden", { count: result.hidden })}</p>}
        <p><a className="button primary" href="#/confirm">{t("review.done.back")}</a></p>
      </section>
    </div>
  );
}

export function ConfirmGroupPage({ route }) {
  const { dataset, version } = route;
  const [state, reload] = useLoad(() => getQueueGroup(dataset, version), [dataset, version]);
  const [marks, setMarks] = useState([]);
  const [picked, setPicked] = useState({});   // {element: {"column|value": "in" | "out"}}
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState(null);
  const group = state.data;
  const lacking = group ? missing(group, marks, picked) : "";
  const asked = group && !lacking && !result ? { dataset, version, items: requestItems(group, picked) } : null;   // once all is seen: what confirming would do to the boards
  const [impact] = useLoad(() => (asked ? previewImpact(asked) : Promise.resolve(null)), [asked]);
  const confirm = async () => {
    setBusy(true);
    setError("");
    try {
      setResult(await confirmGroup(dataset, version, requestItems(group, picked)));
    } catch (e) {
      setError(e.message);
      if (e.code === 409) reload();   // what was read has moved: show what is there now
    }
    setBusy(false);
  };
  return (
    <main className="page has-bar">
      <PageHeader crumbs={[{ label: t("review.page.crumbGroup") }, { label: t("review.page.title"), href: "#/confirm" }, { label: t("review.group.crumbVersion", { dataset, version }) }]}
        title={result ? groupTitle(dataset, version, result.confirmed.length + result.sent_on.length + result.left_out.length) : group ? groupTitle(group.dataset, group.version, group.items.length) : t("review.group.crumbVersion", { dataset, version })}
        sub={group && !result ? t("review.group.sub", { who: group.uploaded_by ?? t("review.group.unknown"), time: timeText(group.uploaded_at) }) : undefined} />
      {state.status === "error" && <p className={state.missing ? "muted" : "error"}>{state.missing ? t("review.group.gone") : state.error} <a href="#/confirm">{t("review.done.back")}</a></p>}
      {state.status === "loading" && !group && <p className="muted">{t("common.loading")}</p>}
      {result && <Done result={result} />}
      {group && !result && (
        <>
          {group.hidden > 0 && <p className="warn">{t("review.group.hiddenNote", { count: group.hidden })}</p>}
          <div className="cards">
            {sortByProblem(group.items).map((item) => (
              <Item key={`${item.element}@${item.version}`} item={item} marks={marks} onMark={(i, on) => setMarks(withMark(marks, i, on))}
                picked={picked[item.element] ?? {}} onPick={(element, key, choice) => setPicked({ ...picked, [element]: { ...(picked[element] ?? {}), [key]: choice } })} />
            ))}
          </div>
          {asked && (
            <section className="card q-impact">
              {impact.status === "loading" && <p className="muted small">{t("review.impact.loading")}</p>}
              {impact.status === "error" && <p className="warn small">{t("review.impact.failed", { error: impact.error })}</p>}
              {impact.status === "ready" && impact.data && <ImpactList impact={impact.data} />}
            </section>
          )}
          <div className="batch-bar" role="region" aria-label={t("review.group.aria")}>
            <button className="secondary" onClick={() => setMarks(group.items.filter((i) => i.ready).reduce((m, i) => withMark(m, i, true), marks))}>{t("review.group.markAll")}</button>
            <span className="batch-spacer" />
            {lacking && <span className="muted small">{lacking}</span>}
            {error && <span className="error">{error}</span>}
            <button className="primary" disabled={busy || Boolean(lacking)} onClick={confirm}>{t("review.group.confirmAll", { count: group.items.filter((i) => i.ready).length })}</button>
          </div>
        </>
      )}
    </main>
  );
}

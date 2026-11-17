import React, { useState } from "react";
import { confirmGroup, getQueueGroup } from "./api.js";
import { KIND, groupTitle, markKey, missing, requestItems, resultLines, withMark } from "./batchModel.js";
import { timeText } from "./format.js";
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
          <tr><th>取值</th><th>上次确认的含义</th><th className="num">行数</th><th>现在的含义</th><th className="num">行数</th></tr>
        </thead>
        <tbody>
          {values.map((v) => (
            <tr key={v.value} className={(v.label_then ?? "") !== v.label || v.rows_then !== v.rows ? "changed" : ""}>
              <td>{v.value}</td>
              <td className="muted">{v.label_then ?? <span className="faint">没有</span>}</td>
              <td className="num muted">{v.rows_then ?? <span className="faint">—</span>}</td>
              <td>{v.label || <span className="faint">还没有含义</span>}</td>
              <td className="num">{v.rows ?? <span className="faint">没有</span>}</td>
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
      <p className="muted small">{stateLine(item, "它") || "需要再看一次"}</p>
      <ul className="checks">
        {item.lines.filter((l) => !item.values || !l.ok).map((l, i) => <li key={i} className={l.ok ? "" : l.strong ? "warn strong" : "warn"}>{l.text}</li>)}
      </ul>
      {item.values && <Values values={item.values} />}
      {item.ready && item.new_values?.map((v) => {
        const key = `${v.column}|${v.value}`;
        return (
          <fieldset key={key} className="new-value">
            <legend>{newValueText(v)}</legend>
            <label><input type="radio" name={`new-${item.element}-${key}`} checked={picked[key] === "in"} onChange={() => onPick(item.element, key, "in")} /> 算进来</label>
            <label><input type="radio" name={`new-${item.element}-${key}`} checked={picked[key] === "out"} onChange={() => onPick(item.element, key, "out")} /> 不算进来</label>
          </fieldset>
        );
      })}
      {item.ready
        ? <label className="check"><input type="checkbox" checked={marks.includes(markKey(item))} onChange={(e) => onMark(item, e.target.checked)} />已看过这一项</label>
        : <p className="warn">这次不会确认它：{item.why_not}</p>}
    </section>
  );
}

function Done({ result }) {
  return (
    <div className="cards">
      <section className="card">
        <ul className="checks">
          {resultLines(result).map((line, i) => <li key={i}>{line}</li>)}
        </ul>
        {result.hidden > 0 && <p className="muted">还有 {result.hidden} 项你看不到，没有动。</p>}
        <p><a className="button primary" href="#/confirm">回到待确认</a></p>
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
    <main className="page">
      <PageHeader crumbs={[{ label: "业务对象" }, { label: "待确认", href: "#/confirm" }, { label: `${dataset} 第 ${version} 版` }]}
        title={result ? groupTitle(dataset, version, result.confirmed.length + result.sent_on.length + result.left_out.length) : group ? groupTitle(group.dataset, group.version, group.items.length) : `${dataset} 第 ${version} 版`}
        sub={group && !result ? `${group.uploaded_by ?? "未署名"} 于 ${timeText(group.uploaded_at)} 上传` : undefined} />
      {state.status === "error" && <p className={state.missing ? "muted" : "error"}>{state.missing ? "这一组已经没有要看的了。" : state.error} <a href="#/confirm">回到待确认</a></p>}
      {state.status === "loading" && !group && <p className="muted">加载中</p>}
      {result && <Done result={result} />}
      {group && !result && (
        <>
          {group.hidden > 0 && <p className="warn">有 {group.hidden} 项你看不到</p>}
          <div className="cards">
            {sortByProblem(group.items).map((item) => (
              <Item key={`${item.element}@${item.version}`} item={item} marks={marks} onMark={(i, on) => setMarks(withMark(marks, i, on))}
                picked={picked[item.element] ?? {}} onPick={(element, key, choice) => setPicked({ ...picked, [element]: { ...(picked[element] ?? {}), [key]: choice } })} />
            ))}
          </div>
          <div className="batch-bar" role="region" aria-label="一起确认">
            <button className="secondary" onClick={() => setMarks(group.items.filter((i) => i.ready).reduce((m, i) => withMark(m, i, true), marks))}>全部标为已看过</button>
            <span className="batch-spacer" />
            {lacking && <span className="muted small">{lacking}</span>}
            {error && <span className="error">{error}</span>}
            <button className="primary" disabled={busy || Boolean(lacking)} onClick={confirm}>一起确认 {group.items.filter((i) => i.ready).length} 项</button>
          </div>
        </>
      )}
    </main>
  );
}

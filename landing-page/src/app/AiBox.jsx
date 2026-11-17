import React, { useState } from "react";
import { aiParse } from "./api.js";
import { t, useT } from "./i18n/index.js";
import { friendlyError } from "./pipelineModel.js";

/** The questions an AI draft could not decide: each with the evidence, the values seen with their rows, and the recommended answer when there is one (a code nobody confirmed has none). An answer is a click. */
export function QuestionList({ questions, answers, onAnswer, busy }) {
  if (!questions.length) return null;
  return (
    <ul className="questions">
      {questions.map((q) => (
        <li key={q.id}>
          <p><strong>{q.ask}</strong></p>
          <p className="muted small">{q.evidence}</p>
          <p className="muted small">{q.recommended ? t("ask.q.suggested", { text: q.recommended.text }) : t("ask.q.noSuggestion")}</p>
          <div className="chips" role="group" aria-label={q.ask}>
            {q.options.map((o) => (
              <button key={o.value} className={`plain${(answers[q.id] ?? []).includes(o.value) ? " on" : ""}`} aria-pressed={(answers[q.id] ?? []).includes(o.value)} disabled={busy} onClick={() => onAnswer(q.id, [o.value])}>{o.text}</button>
            ))}
          </div>
        </li>
      ))}
    </ul>
  );
}

/** What the assistant read to write the draft, said before it is trusted. */
export const SeesNote = ({ sees }) => (sees ? <p className="muted small">{sees.text}{sees.withheld?.length > 0 && t("ask.sees.withheld", { list: sees.withheld.join(t("ask.sep")) })}</p> : null);

/** Describe in one sentence: a sentence into the conditions of a filter (kind "filter") or the name and expression of a calculated column (kind "calc"). A draft: the person applies it. */
export function AiBox({ where, kind, steps, onApply }) {
  const t = useT();
  const [text, setText] = useState("");
  const [state, setState] = useState({ status: "idle" });
  const [answers, setAnswers] = useState({});
  const ask = async (more = {}) => {
    setState((s) => ({ ...s, status: "loading", error: "" }));
    try {
      setState({ status: "ready", data: await aiParse(where.name, where.spec, where.stepId, where.index, kind, text, more) });
    } catch (e) {
      setState({ status: "error", error: e.message });
    }
  };
  const answer = (id, values) => {
    const next = { ...answers, [id]: values };
    setAnswers(next);
    ask({ raw: state.data.raw, answers: next });
  };
  const d = state.data;
  const loading = state.status === "loading";
  return (
    <div className="ai-box">
      <div className="inline">
        <input type="text" aria-label={t("ask.ai.aria")} placeholder={kind === "filter" ? t("ask.ai.placeholderFilter") : t("ask.ai.placeholderCalc")} value={text} onChange={(e) => setText(e.target.value)} />
        <button className="secondary" disabled={!text.trim() || loading} onClick={() => { setAnswers({}); ask(); }}>{loading ? t("ask.ai.writing") : t("ask.ai.parse")}</button>
      </div>
      {state.status === "error" && <p className="error">{friendlyError(state.error, steps ?? [])}</p>}
      {d && (
        <div className="ai-draft">
          <p className="caption">{d.label}{d.basis && t("ask.ai.basis", { basis: d.basis })}</p>
          {d.cites.map((c) => <p key={c.text} className="small">{c.text}</p>)}
          {kind === "filter" && d.where && <pre className="prompt-box">{JSON.stringify(d.where)}</pre>}
          {kind === "calc" && <p><code>{d.name} = {d.expression}</code></p>}
          <QuestionList questions={d.questions} answers={answers} onAnswer={answer} busy={loading} />
          {d.check.ok ? <p className="ok small">{t("ask.ai.checked")}</p> : <p className="bad small">{d.check.error}</p>}
          <SeesNote sees={d.sees} />
          <div className="inline">
            <button className="primary" disabled={!d.check.ok || loading} onClick={() => { onApply(d); setState({ status: "idle" }); setText(""); }}>{t("ask.ai.apply")}</button>
            <button className="plain" onClick={() => setState({ status: "idle" })}>{t("ask.ai.discard")}</button>
          </div>
        </div>
      )}
    </div>
  );
}

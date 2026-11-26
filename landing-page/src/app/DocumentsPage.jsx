import React, { useState } from "react";
import { confirmDocument, fileToBase64, getDocument, getDocuments, uploadDocument } from "./api.js";
import { DOC_ACCEPT, docFileProblem, documentLine, limitsText } from "./documentModel.js";
import { useT } from "./i18n/index.js";
import { useLoad } from "./useLoad.js";
import { EmptyState } from "./ui/EmptyState.jsx";
import { PageHeader } from "./ui/PageHeader.jsx";
import { StatusChip } from "./ui/StatusChip.jsx";

/** The upload form: a file, whether it is for builders only, and what goes to the model, said before anything is sent. */
function UploadForm({ sentToModel, onDone }) {
  const t = useT();
  const [file, setFile] = useState(null);
  const [buildersOnly, setBuildersOnly] = useState(false);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState({ error: "", done: "" });
  const problem = file ? docFileProblem(file) : "";
  const send = async (e) => {
    e.preventDefault();
    setBusy(true);
    setSaid({ error: "", done: "" });
    try {
      const before = await uploadDocument(file.name, await fileToBase64(file), buildersOnly);
      setSaid({ error: "", done: before.state === "confirmed" ? t("documents.upload.same", { name: before.name }) : t("documents.upload.done", { name: before.name }) });
      onDone();
    } catch (err) {
      setSaid({ error: err.message, done: "" });
    }
    setBusy(false);
  };
  return (
    <form className="card doc-upload" onSubmit={send}>
      <h2 className="section">{t("documents.upload.title")}</h2>
      <p className="muted small">{sentToModel || t("documents.sentToModel")}</p>
      <label className="field">
        <span>{t("documents.upload.file")}</span>
        <input type="file" accept={DOC_ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </label>
      <label className="check">
        <input type="checkbox" checked={buildersOnly} onChange={(e) => setBuildersOnly(e.target.checked)} /> {t("documents.upload.buildersOnly")}
        <span className="muted small block">{t("documents.upload.buildersOnlyHint")}</span>
      </label>
      <p className="muted small">{t("documents.upload.sameName")}</p>
      {problem && <p className="error">{problem}</p>}
      {said.error && <p className="error" role="alert">{said.error}</p>}
      {said.done && <p className="ok">{said.done}</p>}
      <button className="primary" disabled={!file || Boolean(problem) || busy}>{busy ? t("documents.upload.sending") : t("documents.upload.send")}</button>
    </form>
  );
}

/** Confirm a document that waits, as the person who reads it: the service refuses the one who put it forward or changed it since. */
function ConfirmButton({ doc, onDone }) {
  const t = useT();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const go = async () => {
    setBusy(true);
    setError("");
    try {
      await confirmDocument(doc.id, doc.version);
      onDone();
    } catch (err) {
      setError(err.message);
    }
    setBusy(false);
  };
  return <>{error && <span className="error block">{error}</span>}<button className="secondary" onClick={go} disabled={busy}>{busy ? t("documents.confirming") : t("documents.confirm")}</button></>;
}

/** The documents this person may read: the list, the upload form for builders, and confirm for what waits. */
export function DocumentsPage() {
  const t = useT();
  const [state, reload] = useLoad(getDocuments, []);
  const data = state.data;
  const docs = data?.documents ?? [];
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("nav.group.data") }, { label: t("documents.title") }]} title={t("documents.title")} sub={t("documents.sub")} />
      {state.status === "error" && <p className="error">{state.error}</p>}
      {state.status === "loading" && !data && <p className="muted">{t("documents.loading")}</p>}
      {data && !data.available && <p className="warn">{data.unavailable || t("documents.unavailable")}</p>}
      {data && <p className="muted small">{limitsText(data.limits)}</p>}
      {data?.available && data.may_upload && <UploadForm sentToModel={data.sent_to_model} onDone={reload} />}
      {data && !docs.length && <EmptyState icon="tasks" title={t("documents.empty.title")} text={data.may_upload ? t("documents.empty.text") : t("documents.empty.viewer")} />}
      {docs.length > 0 && (
        <div className="table-wrap">
          <table>
            <thead><tr><th>{t("documents.col.name")}</th><th>{t("documents.col.state")}</th><th>{t("documents.col.about")}</th><th /></tr></thead>
            <tbody>
              {docs.map((d) => {
                const line = documentLine(d);
                return (
                  <tr key={line.id}>
                    <td><a className="name-link" href={line.href}>{line.name}</a></td>
                    <td><StatusChip state={line.state} /></td>
                    <td className="muted small">{line.meta}{line.by && <span className="block">{line.by}</span>}{line.who && <span className="block">{line.who}</span>}{line.held && <span className="block warn">{line.held}</span>}</td>
                    <td>{line.mayConfirm && <ConfirmButton doc={d} onDone={reload} />}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </main>
  );
}

/** One document: where it stands and its passages, which are what a question finds and the model may quote. */
export function DocumentPage({ route }) {
  const t = useT();
  const [state, reload] = useLoad(() => getDocument(route.id), [route.id]);
  const d = state.data;
  const line = d ? documentLine(d) : null;
  return (
    <main className="page">
      <PageHeader crumbs={[{ label: t("nav.group.data") }, { label: t("documents.title"), href: "#/documents" }, { label: d?.name ?? "" }]} title={d?.name ?? t("documents.title")}
        status={d && <StatusChip state={d.state} />} sub={line ? [line.meta, line.by].filter(Boolean).join(" · ") : ""} />
      {state.status === "error" && <p className="error">{state.missing ? t("documents.notFound") : state.error} <a href="#/documents">{t("documents.back")}</a></p>}
      {state.status === "loading" && !d && <p className="muted">{t("documents.loading")}</p>}
      {line?.who && <p className="muted small">{line.who}</p>}
      {line?.held && <p className="warn small">{line.held}</p>}
      {line?.mayConfirm && <ConfirmButton doc={d} onDone={reload} />}
      {d && (
        <>
          <h2 className="section">{t("documents.passages.title")}</h2>
          <p className="muted small">{t("documents.passages.hint")}</p>
          <ol className="doc-passages">
            {d.passages.map((p) => <li key={p.id} id={p.id}><span className="muted small">{p.where}</span><p>{p.text}</p></li>)}
          </ol>
        </>
      )}
    </main>
  );
}

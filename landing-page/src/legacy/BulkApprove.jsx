import { useState } from "react";

import { BULK_KIND, bulkLabel, bulkProblem, bulkSummary } from "./reviewStackModel.js";

/** The clean band: what can be approved together. The list is shown first, each entry can be left out, and the approval says whose it is. */
export function BulkApprove({ band, client }) {
  const [left, setLeft] = useState(() => new Set());   // entries a person unticked
  const ids = band.map((b) => b.id).filter((id) => !left.has(id));
  const problem = bulkProblem(ids, client.by);
  const toggle = (id) => setLeft((was) => { const next = new Set(was); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  return <details className="os-bulk">
    <summary>{bulkSummary(band)}</summary>
    <ul className="os-bulk-list">{band.map((b) => <li key={b.id}>
      <label><input type="checkbox" checked={!left.has(b.id)} onChange={() => toggle(b.id)} /><b>{b.title}</b><small className="pr-muted">{BULK_KIND[b.kind]}</small></label>
      <ul className="os-open-facts">{b.lines.map((l) => <li key={l}>{l}</li>)}</ul>
    </li>)}</ul>
    <p className="pr-muted">通过后记成“批量确认”，和逐件判断分得开。只放数据能全部核对的关系；代码含义是人对数据的解释，数据证明不了，要逐件看。只有你在这里通过的会记上你的名字，别人之前判过的不动。</p>
    <div className="os-code-save">
      <label>确认人<input value={client.by} maxLength={40} onChange={(e) => client.setBy(e.target.value)} /></label>
      <button type="button" className="pr-primary" disabled={client.busy || !client.can || Boolean(problem)} title={problem || client.why || undefined}
        onClick={() => client.onBulkApprove(ids)}>{client.busy ? "保存中…" : bulkLabel(ids.length)}</button>
    </div>
    {client.error?.key === "bulk" && <p role="alert" className="pr-error">{client.error.text}</p>}
  </details>;
}

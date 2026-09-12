import { useEffect, useState } from 'react';
import { BOUNDARY, DRAFT_KEY, fields, statuses, newDraft, newRow, parseRows, changeRow, recordReview, restoreDraft, saveDraft, summarize, readRecallResponse, checkRows } from './recallWorkspaceModel.js';
import './RecallWorkspace.css';

const labels = { product: '产品名称或公告产品编号', lot: '包装批号', upc: 'UPC（可选，12 位）', label_date: 'Use/Sell By 标签日期（可选）' };
const sampleQueries = [
  { product: 'F-0369-2025/1', lot: 'X7547814', upc: '', label_date: '' },
  { product: 'F-0368-2025/1', lot: '', upc: '', label_date: '' },
  { product: 'F-0368-2025/1', lot: 'X7547814', upc: '', label_date: '' },
];
function Highlight({ text = '', lot = '' }) {
  const value = lot.trim();
  if (!value) return text;
  const index = text.toUpperCase().indexOf(value.toUpperCase());
  return index < 0 ? text : <>{text.slice(0, index)}<mark>{text.slice(index, index + value.length)}</mark>{text.slice(index + value.length)}</>;
}

export function RecallWorkspace({ language = 'zh', onBusyChange }) {
  const [catalog, setCatalog] = useState(null);
  const [draft, setDraft] = useState(null);
  const [selected, setSelected] = useState('');
  const [loadError, setLoadError] = useState('');
  const [storageBlocked, setStorageBlocked] = useState(false);
  const [notice, setNotice] = useState('');
  const [saved, setSaved] = useState('');
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [paste, setPaste] = useState('');
  const [error, setError] = useState('');
  const [filter, setFilter] = useState('all');

  useEffect(() => {
    let active = true;
    setLoadError('');
    fetch('/api/recall/catalog', { cache: 'no-store' }).then(readRecallResponse).then((data) => {
      if (data.schema !== 'public_recall_catalog.v1') throw new Error('公告格式不支持');
      if (!active) return;
      setCatalog(data);
      try {
        const restored = restoreDraft(localStorage.getItem(DRAFT_KEY), data);
        setDraft(restored.draft); setSelected(restored.draft.rows[0]?.id || ''); setNotice(restored.notice); setStorageBlocked(false);
      } catch {
        setStorageBlocked(true); setDraft(null);
        setNotice('本机草稿无法读取或版本不支持，原草稿未覆盖。可先下载原始草稿，再明确重置。');
      }
    }).catch((e) => { if (active) setLoadError(`${e.message} 请检查本地核对服务。`); });
    return () => { active = false; };
  }, [reload]);

  useEffect(() => {
    if (!draft || storageBlocked) return;
    try { saveDraft(localStorage, draft); setSaved('已保存到本机浏览器；切换页面或刷新可恢复。'); }
    catch { setSaved('保存失败：浏览器存储不可用或空间不足。请下载摘要保留本次进度。'); }
  }, [draft, storageBlocked]);

  function download(value, name) {
    const url = URL.createObjectURL(new Blob([value], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = name; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function add(queries) {
    if (draft.rows.length + queries.length > 100) { setError('单个事件最多 100 行。'); return; }
    const rows = queries.map((query) => newRow(query));
    setDraft((current) => ({ ...current, rows: [...current.rows, ...rows] }));
    setSelected(rows[0].id); setFilter('all'); setError('');
  }
  function updateRow(id, updater) {
    setDraft((current) => ({ ...current, rows: current.rows.map((row) => row.id === id ? updater(row) : row) }));
  }
  async function run(rows) {
    setBusy(true);
    onBusyChange?.(true);
    try { await checkRows(rows, (id, patch) => updateRow(id, (current) => ({ ...current, ...patch }))); }
    finally { onBusyChange?.(false); }
    setBusy(false);
  }
  const row = draft?.rows.find((item) => item.id === selected);
  const counts = draft ? summarize(draft) : null;
  const visibleRows = draft?.rows.filter((item) => filter === 'all' || (filter === 'needs_evidence' ? item.review?.choice === filter : (item.result?.status || 'pending') === filter));

  return <section className="recall-workspace" aria-labelledby="recall-title">
    <header><span className="recall-eyebrow">公开历史案例 · OPENFDA 95876</span><h1 id="recall-title">{language === 'en' ? 'Recall event worklist' : '把待核对批次逐项处理完'}</h1><p>Russ Davis · 2024 年黄瓜及加工食品召回。添加待核对清单 → 查看公告依据 → 修正信息与复核 → 保存摘要。</p></header>
    <p className="recall-boundary">{BOUNDARY}</p>
    {loadError ? <p role="alert">{loadError} <button onClick={() => setReload((n) => n + 1)}>重新连接</button></p> : !catalog ? <p role="status">读取公告中…</p> : <>
      {notice && <p role="status">{notice}</p>}
      {storageBlocked && <div className="recall-error"><button onClick={() => { try { download(localStorage.getItem(DRAFT_KEY) || '', 'recall-original-draft.json'); } catch { setNotice('浏览器禁止读取存储，无法下载原草稿。'); } }}>下载原始草稿</button><button onClick={() => { if (window.confirm('重置会替换本机事件 95876 草稿。已保留需要的原始草稿吗？')) { setDraft(newDraft(catalog)); setStorageBlocked(false); setNotice('已新建空白草稿。'); } }}>重置本机草稿</button></div>}
      {draft && <>
        <div className="recall-form-actions">
          <button disabled={busy || draft.rows.length >= 100} onClick={() => add([undefined])}>添加一行</button>
          <button disabled={busy || draft.rows.length > 97} onClick={() => { add(sampleQueries); setNotice('已添加 3 行练习输入，含缺失和冲突情况；这些行不是实际库存。'); }}>添加 3 行练习示例</button>
          <button className="recall-primary" disabled={busy || !counts.pending} onClick={() => run(draft.rows.filter((item) => !item.result))}>{busy ? '正在逐行核对…' : `核对待处理行（${counts.pending}）`}</button>
          <button disabled={busy || !counts.total} onClick={() => download(JSON.stringify({ ...draft, exported_at: new Date().toISOString(), boundary: BOUNDARY, summary: counts }, null, 2), 'recall-95876-summary.json')}>下载核对摘要</button>
        </div>
        <details className="recall-paste"><summary>从表格粘贴多行（最多 100 行）</summary><p>不含表头，按顺序粘贴 4 列：产品名称或公告编号、批号、UPC、标签日期（YYYY-MM-DD）。用 Tab 分隔，缺少的单元格留空。</p><textarea aria-label="批量粘贴" value={paste} onChange={(e) => setPaste(e.target.value)} disabled={busy} /><button disabled={busy} onClick={() => { try { add(parseRows(paste, draft.rows.length)); setPaste(''); } catch (e) { setError(e.message); } }}>加入核对清单</button></details>
        {error && <p role="alert" className="recall-error">{error}</p>}
        <p role="status" className="recall-save-status">{saved} 复核 {counts.reviewed}/{counts.total} · 需补证 {counts.needs_evidence}</p>
        <div className="recall-counts" aria-label="清单筛选">{[['all', '全部', counts.total], ['pending', '待核对', counts.pending], ...Object.entries(statuses).map(([key, label]) => [key, label, counts[key]]), ['needs_evidence', '需补证', counts.needs_evidence]].map(([key, label, count]) => <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>{label} {count}</button>)}</div>
        {!draft.rows.length ? <p className="recall-empty">清单还是空的。添加一行，或用 3 行练习示例体验“缺信息 → 补全 → 重新核对”。</p> : <div className="recall-worklist-layout">
          <div className="recall-rows" aria-label="待核对清单">{visibleRows.length ? visibleRows.map((item) => <button key={item.id} className="recall-row" aria-pressed={row?.id === item.id} onClick={() => setSelected(item.id)}><strong>第 {draft.rows.indexOf(item) + 1} 行 · {catalog.products.find((p) => p.product_key === item.query.product)?.name || item.query.product || '未填写产品'}</strong><span>批号：{item.query.lot || '待补充'} · {statuses[item.result?.status] || '待核对'}</span><small>{item.error || (item.review?.choice === 'needs_evidence' ? `需补证：${item.review.followup}` : item.review ? '已复核' : '尚未复核')}</small></button>) : <p>该分类暂无条目。</p>}</div>
          {row && <article className="recall-row-detail" aria-label="当前行详情"><h2>第 {draft.rows.indexOf(row) + 1} 行 · 核对与复核</h2>
            <fieldset className="recall-fields" disabled={busy}>{fields.map((field) => <label key={field}>{labels[field]}<input aria-label={labels[field]} list={field === 'product' ? 'recall-products' : undefined} type={field === 'label_date' ? 'date' : 'text'} maxLength={300} value={row.query[field]} onChange={(e) => setDraft((current) => changeRow(current, row.id, field, e.target.value))} /></label>)}<datalist id="recall-products">{catalog.products.map((p) => <option key={p.product_key} value={p.product_key}>{p.name}</option>)}</datalist><p className="recall-date-hint">修改任一条件后，该行旧结果及复核失效。标签日期不是生产日期。</p></fieldset>
            <button className="recall-primary" disabled={busy} onClick={() => run([row])}>核对当前行</button>
            {row.error && <p role="alert">{row.error} 可点击“核对当前行”重试。</p>}
            {row.result && <div className={`recall-result recall-${row.result.status}`}><h3>{statuses[row.result.status]}</h3><p>{row.result.reason}</p>
              <ul className="recall-conditions"><li>产品 / UPC：{row.query.product || row.query.upc || '未提供'}；{row.query.upc ? `UPC 已提交 ${row.query.upc}` : '未提供 UPC，未独立核对条码'}</li><li>批号：{row.query.lot || '未提供，待补充'}</li><li>标签日期：{row.query.label_date ? `${row.query.label_date}（已提交核对，见上述结论）` : '未提供，未核对日期条件'}</li></ul>
              <details><summary>查看公告原文与批号依据</summary>{row.result.evidence.map((e) => <section className="recall-evidence" key={e.product_key}><h4>{e.name} · {e.recall_number}</h4><p>{e.description_quote}</p><p><Highlight text={e.code_quote} lot={row.query.lot} /></p><p>分销范围：{e.distribution_pattern}</p></section>)}<a href={catalog.source_url} target="_blank" rel="noreferrer">openFDA 原始记录</a></details>
              <Review key={`${row.id}:${JSON.stringify(row.query)}:${JSON.stringify(row.result)}`} row={row} busy={busy} onSave={(review) => updateRow(row.id, (current) => recordReview(current, review))} />
            </div>}
          </article>}
        </div>}
      </>}
      <footer><a href={catalog.source_url} target="_blank" rel="noreferrer">openFDA 原始记录</a><span>数据获取时间：{catalog.retrieved_at}</span></footer>
    </>}
  </section>;
}
function Review({ row, busy, onSave }) {
  const [review, setReview] = useState(row.review || { choice: 'agree', reason: '', followup: '', handler: '' });
  const [error, setError] = useState('');
  const [dirty, setDirty] = useState(false);
  return <form className="recall-review" onChange={() => setDirty(true)} onSubmit={(e) => { e.preventDefault(); try { onSave(review); setDirty(false); setError(''); } catch (err) { setError(err.message); } }}><h3>人工复核</h3>{dirty && <p role="status">复核编辑尚未保存，请点击“保存本行复核”。</p>}<fieldset disabled={busy}>
    <label>复核结论<select value={review.choice} onChange={(e) => setReview({ ...review, choice: e.target.value })}><option value="agree">认可核对结果</option><option value="needs_evidence">需要补充证据</option></select></label>
    <label>复核理由<textarea required maxLength={1000} value={review.reason} onChange={(e) => setReview({ ...review, reason: e.target.value })} /></label>
    {review.choice === 'needs_evidence' && <label>需要补充的证据<input required maxLength={1000} value={review.followup} onChange={(e) => setReview({ ...review, followup: e.target.value })} placeholder="例如：包装标签照片、准确批号" /></label>}
    <label>经办人备注（可选，未经身份验证）<input maxLength={100} value={review.handler} onChange={(e) => setReview({ ...review, handler: e.target.value })} /></label>
    <button type="submit">保存本行复核</button></fieldset>{error && <p role="alert">{error}</p>}{row.review && <p>已记录：{row.review.choice === 'needs_evidence' ? `需补证 · ${row.review.followup}` : '认可结果'} · {row.review.reason}</p>}
  </form>;
}

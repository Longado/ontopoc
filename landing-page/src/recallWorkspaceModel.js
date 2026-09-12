export function editQuery(state, field, value) {
  return { ...state, query: { ...state.query, [field]: value }, result: null, review: null, error: '' };
}

export async function readRecallResponse(response) {
  let data;
  try { data = await response.json(); }
  catch { throw new Error('请启动本地核对服务后重试 / Start the local recall service.'); }
  if (!response.ok) throw new Error(data.error || '本地核对服务暂不可用 / Recall service unavailable.');
  return data;
}

export async function requestMatch(query, fetcher = fetch) {
  const response = await fetcher('/api/recall/match', {
    method: 'POST', signal: AbortSignal.timeout(15000), headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(query),
  });
  const data = await readRecallResponse(response);
  if (data.schema !== 'public_recall_match.v1') throw new Error('本地核对服务返回了不支持的数据。');
  return data;
}

export const DRAFT_KEY = 'ontopoc.recall-worklist.v1.95876';
export const BOUNDARY = '仅核对 openFDA 历史事件 95876；未匹配不代表安全。复核及经办人是本机备注，不代表审批、身份认证或库存已控制。';
export const fields = ['product', 'lot', 'upc', 'label_date'];
export const statuses = { matched: '匹配公告范围', insufficient: '缺信息', conflict: '信息冲突', not_matched: '未匹配本公告' };
export const emptyQuery = () => Object.fromEntries(fields.map((key) => [key, '']));
export const catalogVersion = (catalog) => JSON.stringify([catalog.retrieved_at, catalog.products]);
export const newDraft = (catalog) => ({ schema: 'recall_worklist.v1', event_id: '95876', catalogVersion: catalogVersion(catalog), rows: [] });
export const newRow = (query = emptyQuery(), id = crypto.randomUUID()) => ({ id, query, result: null, review: null, error: '' });

export function parseRows(text, currentCount = 0) {
  const lines = text.split(/\r?\n/).filter((line) => line.trim());
  if (!lines.length) throw new Error('请粘贴至少一行。');
  if (lines.length + currentCount > 100) throw new Error('单个事件最多 100 行。');
  return lines.map((line, index) => {
    const cells = line.split('\t').map((cell) => cell.trim());
    if (cells.length > 4 || cells.some((cell) => cell.length > 300)) throw new Error(`第 ${index + 1} 行须为最多 4 列，每格不超过 300 字。`);
    return Object.fromEntries(fields.map((field, i) => [field, cells[i] || '']));
  });
}

export function changeRow(draft, id, field, value) {
  return { ...draft, rows: draft.rows.map((row) => row.id === id ? editQuery(row, field, value) : row) };
}

export function recordReview(row, review) {
  if (!row.result || !['agree', 'needs_evidence'].includes(review.choice) || !review.reason?.trim()) throw new Error('先核对，并填写复核理由。');
  if (review.choice === 'needs_evidence' && !review.followup?.trim()) throw new Error('请填写需要补充的证据。');
  return { ...row, review: { ...review, reason: review.reason.trim(), updated_at: new Date().toISOString() } };
}

export function restoreDraft(raw, catalog) {
  if (raw === null) return { draft: newDraft(catalog), notice: '' };
  const draft = JSON.parse(raw);
  if (!draft || draft.schema !== 'recall_worklist.v1' || draft.event_id !== '95876' || typeof draft.catalogVersion !== 'string' || !Array.isArray(draft.rows) || draft.rows.length > 100) throw new Error('草稿格式或版本不支持');
  const ids = new Set();
  for (const row of draft.rows) {
    if (!row || typeof row.id !== 'string' || ids.has(row.id) || !row.query || fields.some((f) => typeof row.query[f] !== 'string' || row.query[f].length > 300)) throw new Error('草稿行格式错误');
    ids.add(row.id);
    if (row.result && (row.result.schema !== 'public_recall_match.v1' || !statuses[row.result.status] || !Array.isArray(row.result.evidence) || !row.result.query)) throw new Error('草稿结果格式错误');
    if (row.result) {
      const normalized = (query, field) => {
        const value = query[field]?.trim();
        return field === 'lot' ? value?.toUpperCase() : field === 'upc' ? value?.replace(/[\s-]/g, '') : value;
      };
      if (fields.some((field) => normalized(row.query, field) !== normalized(row.result.query, field))) throw new Error('草稿结果与输入不一致');
      if (row.result.evidence.some((e) => !e || ['product_key', 'name', 'recall_number', 'description_quote', 'code_quote', 'distribution_pattern'].some((f) => typeof e[f] !== 'string'))) throw new Error('草稿依据格式错误');
    }
    if (row.review && (!row.result || !['agree', 'needs_evidence'].includes(row.review.choice) || typeof row.review.reason !== 'string' || (row.review.choice === 'needs_evidence' && !row.review.followup?.trim()))) throw new Error('草稿复核格式错误');
  }
  if (draft.catalogVersion !== catalogVersion(catalog)) return { draft: { ...newDraft(catalog), rows: draft.rows.map((row) => ({ ...row, result: null, review: null, error: '' })) }, notice: '公告版本已变化；保留输入，请重新核对和复核。' };
  return { draft, notice: draft.rows.length ? '已恢复本机草稿。' : '' };
}

export function saveDraft(storage, draft) { storage.setItem(DRAFT_KEY, JSON.stringify(draft)); }
export function summarize(draft) {
  const counts = { total: draft.rows.length, pending: 0, matched: 0, insufficient: 0, conflict: 0, not_matched: 0, needs_evidence: 0, reviewed: 0 };
  for (const row of draft.rows) {
    counts[row.result?.status || 'pending']++;
    if (row.review?.choice === 'needs_evidence') counts.needs_evidence++;
    if (row.review) counts.reviewed++;
  }
  return counts;
}

export async function checkRows(rows, update, matcher = requestMatch) {
  for (const row of rows) {
    update(row.id, { result: null, review: null, error: '' });
    try { update(row.id, { result: await matcher(row.query) }); }
    catch (e) { update(row.id, { error: e.message || '核对失败，请重试。' }); }
  }
}

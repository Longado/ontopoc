import assert from 'node:assert/strict';
import test from 'node:test';
import { existsSync } from 'node:fs';

async function model() {
  assert.ok(existsSync(new URL('./recallWorkspaceModel.js', import.meta.url)), 'recall UI model is not implemented');
  return import('./recallWorkspaceModel.js');
}

test('editing inputs clears the prior result and human review', async () => {
  const { editQuery } = await model();
  const changed = editQuery({ query: { product: 'p', lot: 'a' }, result: { status: 'matched' },
    review: { choice: 'agree', reason: 'checked' }, error: 'old' }, 'lot', 'b');
  assert.equal(changed.query.lot, 'b');
  assert.equal(changed.result, null);
  assert.equal(changed.review, null);
  assert.equal(changed.error, '');
});

test('client displays server results without computing a match', async () => {
  const { requestMatch } = await model();
  const result = await requestMatch({ product: 'p', lot: 'a' }, async (url, options) => {
    assert.equal(url, '/api/recall/match');
    assert.deepEqual(JSON.parse(options.body), { product: 'p', lot: 'a' });
    return { ok: true, json: async () => ({ schema: 'public_recall_match.v1', status: 'conflict', reason: 'server result' }) };
  });
  assert.equal(result.status, 'conflict');
});

test('server errors and non-JSON static-host responses are actionable', async () => {
  const { requestMatch } = await model();
  await assert.rejects(requestMatch({}, async () => ({ ok: false, json: async () => ({ error: 'bad input' }) })), /bad input/);
  await assert.rejects(requestMatch({}, async () => ({ ok: true, json: async () => { throw new Error('html'); } })), /本地核对服务/);
});

test('tabular intake preserves missing cells and rejects overflow', async () => {
  const { parseRows } = await model();
  assert.deepEqual(parseRows('p\t\tu\t2024-11-20')[0], { product: 'p', lot: '', upc: 'u', label_date: '2024-11-20' });
  assert.throws(() => parseRows('p\ta\tb\tc\textra'), /4/);
  assert.throws(() => parseRows(Array(101).fill('p\ta').join('\n')), /100/);
});

test('row correction invalidates only that row and review requires a follow-up', async () => {
  const { changeRow, recordReview } = await model();
  const a = { id: 'a', query: { product: 'p', lot: 'a' }, result: { status: 'matched' }, review: { choice: 'agree' } };
  const b = { ...a, id: 'b' };
  const changed = changeRow({ rows: [a, b] }, 'a', 'lot', 'new');
  assert.equal(changed.rows[0].result, null);
  assert.equal(changed.rows[0].review, null);
  assert.equal(changed.rows[1], b);
  assert.throws(() => recordReview(a, { choice: 'needs_evidence', reason: 'unclear' }), /补充/);
  assert.equal(recordReview(a, { choice: 'needs_evidence', reason: 'unclear', followup: 'label photo' }).review.followup, 'label photo');
});

test('draft restoration keeps progress, invalidates old sources and protects malformed storage', async () => {
  const { newDraft, newRow, restoreDraft, saveDraft } = await model();
  const catalog = { event_id: '95876', retrieved_at: 'today', products: [] };
  const draft = newDraft(catalog);
  draft.rows = [newRow({ product: 'p', lot: 'a', upc: '', label_date: '' }, 'one')];
  draft.rows[0].result = { schema: 'public_recall_match.v1', status: 'matched', evidence: [], query: draft.rows[0].query };
  draft.rows[0].review = { choice: 'agree', reason: 'checked' };
  assert.deepEqual(restoreDraft(JSON.stringify(draft), catalog).draft, draft);
  const refreshed = restoreDraft(JSON.stringify(draft), { ...catalog, retrieved_at: 'tomorrow' });
  assert.equal(refreshed.draft.rows[0].result, null);
  assert.equal(refreshed.draft.rows[0].review, null);
  assert.throws(() => restoreDraft('{bad', catalog));
  assert.throws(() => restoreDraft(JSON.stringify({ ...draft, schema: 'future' }), catalog));
  assert.throws(() => restoreDraft(JSON.stringify({ ...draft, rows: [draft.rows[0], draft.rows[0]] }), catalog));
  assert.throws(() => saveDraft({ setItem() { throw new Error('quota'); } }, draft), /quota/);
});

test('a failed row does not stop remaining rows or erase prior results', async () => {
  const { checkRows } = await model();
  const changes = [];
  await checkRows([{ id: 'a', query: { lot: 'bad' } }, { id: 'b', query: { lot: 'ok' } }], (id, patch) => changes.push([id, patch]), async (q) => {
    if (q.lot === 'bad') throw new Error('service error');
    return { status: 'matched' };
  });
  assert.equal(changes.find(([id, p]) => id === 'a' && p.error)[1].error, 'service error');
  assert.equal(changes.find(([id, p]) => id === 'b' && p.result)[1].result.status, 'matched');
});

test('stored results cannot be attached to a different input row', async () => {
  const { newDraft, newRow, restoreDraft } = await model();
  const catalog = { retrieved_at: 'today', products: [] };
  const draft = newDraft(catalog);
  const row = newRow({ product: 'p', lot: 'x1', upc: '', label_date: '' }, 'row');
  row.result = { schema: 'public_recall_match.v1', status: 'matched', query: { ...row.query, lot: 'OLD' }, evidence: [] };
  draft.rows = [row];
  assert.throws(() => restoreDraft(JSON.stringify(draft), catalog), /输入/);
  row.result.query.lot = 'X1';
  assert.equal(restoreDraft(JSON.stringify(draft), catalog).draft.rows.length, 1);
});

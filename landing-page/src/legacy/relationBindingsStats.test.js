import assert from 'node:assert/strict';
import test from 'node:test';
import { edgeStats } from './ontologyGraphModel.js';

test('an empty parent reference is separate from an unresolved nonempty reference', () => {
  const fit = { relations: [{ key: 'reports', rows: 8, linked_rows: 7, empty_rows: 1 }] };
  assert.equal(edgeStats(fit, 'reports').complete, true);
  assert.equal(edgeStats(fit, 'reports').empty_rows, 1);
  fit.relations[0].linked_rows = 6;
  assert.equal(edgeStats(fit, 'reports').complete, false);
});

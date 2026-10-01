import assert from 'node:assert/strict';
import test from 'node:test';
import * as model from './ontologyStudioModel.js';

test('unresolved relation references identify the actual reference column and target', () => {
  assert.equal(typeof model.missingReferenceFeedback, 'function');
  const ontology = { object_types: [{ key: 'employee', label: '员工' }], relations: [{ key: 'reviewed_by', label: '复核' }] };
  const from = { type: 'employee', source: 'Assignment', relation: 'reviewed_by', endpoint: 'from', fields: ['OwnerId'], count: 1 };
  const to = { ...from, endpoint: 'to', fields: ['ReviewerId'] };
  const feedback = model.missingReferenceFeedback(ontology, to);
  assert.match(feedback.title, /Assignment.*ReviewerId.*1.*员工/);
  assert.match(feedback.title, /复核.*终点/);
  assert.notEqual(feedback.key, model.missingReferenceFeedback(ontology, from).key);
});

test('legacy missing-source findings keep the original source wording', () => {
  assert.equal(typeof model.missingReferenceFeedback, 'function');
  const ontology = { object_types: [{ key: 'employee', label: '员工' }] };
  const feedback = model.missingReferenceFeedback(ontology, { type: 'employee', source: 'Employee', count: 2 });
  assert.equal(feedback.title, '员工：2 个不在"Employee"表里');
});

import assert from 'node:assert/strict';
import { test } from 'node:test';
import * as model from './ontologyReferenceModel.js';
const run = { saved_as: 'run.json', ontology: { object_types: [{ key: 'customer', label: '客户' }], relations: [] }, confirmation: { decisions: { types: { customer: 'ok' } } }, evaluation: { handover: { sources: [{ name: 'customers', fields: [{ path: 'id', type: 'INTEGER' }] }] } } };
test('equivalent API responses and QA answers preserve the domain draft revision', () => {
  assert.equal(typeof model.referenceRevision, 'function');
  const updated = JSON.parse(JSON.stringify(run));
  updated.ontology = { relations: [], object_types: [{ label: '客户', key: 'customer' }] };
  updated.evaluation.asked = [{ question: '客户有多少？' }];
  updated.confirmation.confirmed_at = 'a later timestamp';
  assert.equal(model.referenceRevision(updated), model.referenceRevision(run));
});
test('changed ontology, decisions, field declarations or saved mapping refresh the reference context', () => {
  assert.equal(typeof model.referenceRevision, 'function');
  for (const change of [
    r => { r.ontology.object_types[0].label = '购买客户'; },
    r => { r.confirmation.decisions.types.customer = 'wrong'; },
    r => { r.evaluation.handover.sources[0].fields[0].type = 'VARCHAR'; },
    r => { r.evaluation.domain_reference = { reference_id: 'ecommerce', mappings: [] }; },
  ]) {
    const updated = structuredClone(run); change(updated);
    assert.notEqual(model.referenceRevision(updated), model.referenceRevision(run));
  }
});

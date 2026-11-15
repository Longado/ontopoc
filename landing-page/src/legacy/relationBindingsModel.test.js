import assert from 'node:assert/strict';
import test from 'node:test';
import * as model from './ontologyStudioModel.js';

test('a relation shows its actual source columns in direction order', () => {
  assert.equal(typeof model.relationBindingLine, 'function');
  assert.equal(model.relationBindingLine({ source: 'Employee', from_identity: { id: 'EmployeeId' }, to_identity: { id: 'ReportsTo' } }), 'Employee：EmployeeId → ReportsTo');
  assert.equal(model.relationBindingLine({ source: 'Orders' }), '');
});

test('the last failed attempt remains visible with a concrete correction', () => {
  assert.equal(typeof model.verificationIssues, 'function');
  const relation = { key: 'reports_to', from: 'employee', to: 'employee' };
  const ontology = { object_types: [{ key: 'employee', label: '员工' }], relations: [relation],
    verification: { errors: [{ code: 'relation_binding_invalid', relation: 'reports_to', endpoint: 'to', source: 'Employee', fields: ['Missing'], hint: '请选择该表实际存在的上级编号列。', message: 'raw backend detail' }] } };
  const issues = model.verificationIssues(ontology);
  assert.equal(issues.length, 1);
  assert.match(issues[0].title, /关系端点绑定不正确/);
  assert.match(issues[0].location, /员工.*Employee.*Missing/);
  assert.equal(issues[0].hint, '请选择该表实际存在的上级编号列。');
  assert.deepEqual(model.verificationIssues({ verification: { errors: [] } }), []);
});

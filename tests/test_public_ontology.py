import copy
import importlib
import json
from pathlib import Path
import unittest

FIXTURES = Path(__file__).resolve().parent / 'fixtures/nhtsa'


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))


def component(name):
    return ('component', (('component_name', name),))


def vehicle(model, year):
    return ('vehicle_model_year', (('make', 'CHEVROLET'), ('model', model), ('model_year', year)))


class PublicOntologyVerificationTests(unittest.TestCase):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('ontology_poc_generator.public_ontology'),
                             'public ontology verification is not implemented')
        return importlib.import_module('ontology_poc_generator.public_ontology')

    def setUp(self):
        self.bundle = load('mini_bundle.json')
        self.proposal = load('reference_proposal.json')

    def codes(self, proposal=None, bundle=None):
        result = self.api().verify_proposal(self.proposal if proposal is None else proposal,
                                            self.bundle if bundle is None else bundle)
        return {e['code'] for e in result['errors']}

    def type_of(self, proposal, key):
        return next(t for t in proposal['object_types'] if t['key'] == key)

    def test_reference_proposal_passes_and_is_not_mutated(self):
        before = copy.deepcopy(self.proposal)
        result = self.api().verify_proposal(self.proposal, self.bundle)
        self.assertEqual(result['errors'], [])
        self.assertEqual(self.proposal, before)

    def test_malformed_response_is_invalid_response(self):
        for bad in [[], {'object_types': 'x', 'relations': []}, {'relations': []},
                    {'object_types': [1], 'relations': []}]:
            with self.subTest(bad=bad):
                self.assertIn('invalid_response', self.codes(bad))

    def test_unknown_source_and_unknown_field(self):
        p = copy.deepcopy(self.proposal)
        self.type_of(p, 'complaint')['populated_from'][0]['identity'] = {'odi_number': 'odi'}
        self.assertIn('unknown_field', self.codes(p))
        p = copy.deepcopy(self.proposal)
        self.type_of(p, 'complaint')['populated_from'][0]['source'] = 'tweets'
        self.assertIn('unknown_source', self.codes(p))

    def test_field_present_but_always_empty(self):
        b = copy.deepcopy(self.bundle)
        for r in b['sources']['recalls']['records']:
            r['Component'] = ''
        self.assertIn('empty_field', self.codes(bundle=b))

    def test_same_type_must_use_same_logical_keys_across_sources(self):
        p = copy.deepcopy(self.proposal)
        ident = self.type_of(p, 'vehicle_model_year')['populated_from'][1]['identity']
        ident['year'] = ident.pop('model_year')
        self.assertIn('identity_keys_mismatch', self.codes(p))

    def test_every_field_must_be_used_or_ignored(self):
        p = copy.deepcopy(self.proposal)
        t = self.type_of(p, 'complaint')
        t['attributes'] = [a for a in t['attributes'] if a['path'] != 'summary']
        self.assertIn('field_unaccounted', self.codes(p))

    def test_each_role_needs_exactly_one_type(self):
        p = copy.deepcopy(self.proposal)
        self.type_of(p, 'vehicle')['role'] = 'signal'
        self.assertIn('role_count', self.codes(p))
        p = copy.deepcopy(self.proposal)
        self.type_of(p, 'recall_campaign')['role'] = 'context'
        self.assertIn('role_count', self.codes(p))

    def test_transform_needs_single_identity_field(self):
        p = copy.deepcopy(self.proposal)
        self.type_of(p, 'vehicle_model_year')['populated_from'][0]['transform'] = 'split_comma'
        self.assertIn('transform_needs_single_field', self.codes(p))

    def test_identity_cannot_mix_two_lists(self):
        p = copy.deepcopy(self.proposal)
        ident = self.type_of(p, 'vehicle_model_year')['populated_from'][1]['identity']
        ident['make'] = 'recalls[].Make'
        self.assertIn('mixed_list_identity', self.codes(p))

    def test_relation_endpoints_must_exist_in_the_named_source(self):
        p = copy.deepcopy(self.proposal)
        next(r for r in p['relations'] if r['key'] == 'recall_targets_component')['source'] = 'complaints'
        self.assertIn('relation_source_mismatch', self.codes(p))
        p = copy.deepcopy(self.proposal)
        p['relations'][0]['from'] = 'nope'
        self.assertIn('relation_unknown_type', self.codes(p))

    def test_relation_without_links_in_data(self):
        p = copy.deepcopy(self.proposal)
        b = copy.deepcopy(self.bundle)
        records = b['sources']['complaints']['records']
        for r in records[1:]:
            r['vin'] = None
        records[0]['components'] = ''
        p['relations'].append({'key': 'vehicle_has_component', 'from': 'vehicle', 'to': 'component',
                               'source': 'complaints', 'meaning': 'test'})
        self.assertEqual(self.codes(p, b), {'relation_zero_links'})

    def test_scope_question_needs_the_four_role_relations(self):
        p = copy.deepcopy(self.proposal)
        p['relations'] = [r for r in p['relations'] if r['key'] != 'complaint_is_about_model_year']
        self.assertIn('role_relation_missing', self.codes(p))

    def test_sources_must_share_affected_objects(self):
        b = copy.deepcopy(self.bundle)
        for r in b['sources']['complaints']['records']:
            for product in r['products']:
                product['productModel'] = 'OTHER CAR'
        self.assertIn('sources_not_connected', self.codes(bundle=b))


class PublicOntologyGraphTests(unittest.TestCase):
    def setUp(self):
        self.api = importlib.import_module('ontology_poc_generator.public_ontology')
        self.bundle = load('mini_bundle.json')
        self.proposal = load('reference_proposal.json')

    def test_colon_path_creates_parent_components(self):
        g = self.api.build_graph(self.proposal, self.bundle)
        full = component('ELECTRICAL SYSTEM:PROPULSION SYSTEM:TRACTION BATTERY')
        self.assertIn((full, component('ELECTRICAL SYSTEM:PROPULSION SYSTEM')), g['part_of'])
        self.assertIn((component('ELECTRICAL SYSTEM:PROPULSION SYSTEM'), component('ELECTRICAL SYSTEM')), g['part_of'])
        self.assertEqual(self.api.ancestors(g, full),
                         [component('ELECTRICAL SYSTEM:PROPULSION SYSTEM'), component('ELECTRICAL SYSTEM')])

    def test_comma_list_splits_into_components(self):
        g = self.api.build_graph(self.proposal, self.bundle)
        signal = ('complaint', (('odi_number', '11600123'),))
        linked = self.api.linked(g, signal, 'component')
        self.assertEqual(linked, {component('ELECTRICAL SYSTEM'), component('SEATS'), component('UNKNOWN OR OTHER')})

    def test_values_are_normalized_before_merging(self):
        b = copy.deepcopy(self.bundle)
        target = next(r for r in b['sources']['complaints']['records'] if r['odiNumber'] == 11429891)
        target['products'][0]['productModel'] = '  bolt   ev '
        g = self.api.build_graph(self.proposal, b)
        self.assertEqual(g['sources_of'][vehicle('BOLT EV', '2020')], {'recalls', 'complaints'})

    def test_shared_objects_match_hand_count(self):
        g = self.api.build_graph(self.proposal, self.bundle)
        shared = {i for i, s in g['sources_of'].items() if len(s) > 1}
        self.assertEqual(shared, {vehicle('BOLT EV', '2019'), vehicle('BOLT EV', '2020'),
                                  component('ELECTRICAL SYSTEM'), component('AIR BAGS')})


class SharedCoreStandsAloneTests(unittest.TestCase):
    def test_the_shared_core_hashes_a_bundle_itself_without_the_recall_sources_module(self):
        import ast
        core = importlib.import_module('ontology_poc_generator.public_ontology')
        # the same canonical JSON and SHA-256 as before, so hashes kept in saved runs still match
        self.assertEqual(core.bundle_content_hash({'b': ['x'], 'a': 1}),
                         'fd5e92badbe24726f55b88132dd5fa1ceec0efd960b3bcd44f527b4bcc84af34')
        tree = ast.parse(Path(core.__file__).read_text(encoding='utf-8'))
        imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
        self.assertEqual([name for name in imported if 'nhtsa' in (name or '')], [])


class ValueAliasGraphTests(unittest.TestCase):
    """A confirmed name pair (value_aliases) makes two spellings one object, for the rows that describe it and for relation ends."""
    BUNDLE = {'sources': {'depts': {'records': [{'dept': 'PLANNING'}]}, 'ledger': {'records': [{'row': '1', 'dept': 'PLAN & DEV'}]}}}
    PROPOSAL = {'object_types': [
        {'key': 'dept', 'label': '部门', 'populated_from': [{'source': 'depts', 'identity': {'name': 'dept'}},
                                                           {'source': 'ledger', 'identity': {'name': 'dept'}}]},
        {'key': 'entry', 'label': '支出行', 'populated_from': [{'source': 'ledger', 'identity': {'row': 'row'}}]}],
        'relations': [{'key': 'entry_dept', 'from': 'entry', 'to': 'dept', 'source': 'ledger', 'to_identity': {'name': 'dept'}}]}
    ALIAS = {'type': 'dept', 'source': 'ledger', 'value': 'PLAN & DEV', 'target_source': 'depts', 'target_value': 'PLANNING'}

    def graph(self, aliases):
        return importlib.import_module('ontology_poc_generator.public_ontology').build_graph({**self.PROPOSAL, 'value_aliases': aliases}, self.BUNDLE)

    def test_without_a_pair_the_two_spellings_stay_two_objects(self):
        g = self.graph([])
        self.assertEqual(g['sources_of'][('dept', (('name', 'PLAN & DEV'),))], {'ledger'})
        self.assertEqual(g['sources_of'][('dept', (('name', 'PLANNING'),))], {'depts'})
        self.assertEqual(g['aliased'], set())

    def test_a_pair_makes_one_object_from_both_sources_and_the_relation_reaches_it(self):
        g = self.graph([self.ALIAS])
        planning = ('dept', (('name', 'PLANNING'),))
        self.assertEqual(g['sources_of'][planning], {'depts', 'ledger'})
        self.assertNotIn(('dept', (('name', 'PLAN & DEV'),)), g['sources_of'])
        self.assertEqual(g['aliased'], {('ledger', 0, planning)})
        self.assertEqual({(a, b) for a, b, _ in g['edges']['entry_dept']}, {(('entry', (('row', '1'),)), planning)})
        self.assertEqual(g['missing_references'], [])


if __name__ == '__main__':
    unittest.main()

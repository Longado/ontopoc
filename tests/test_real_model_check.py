"""How the real-model check scores an answer: right, wrong (a number that does not match the rows), missed (refused or not answered, which is
never a wrong number) or error. Only a wrong number fails the check."""
import unittest

from scripts.real_model_check import judge


class JudgeTests(unittest.TestCase):
    def test_a_count_a_sum_and_ranked_groups_are_compared_with_the_truth(self):
        self.assertEqual(judge({'expect': 'count', 'truth': 16}, 200, {'status': 'answered', 'answer': {'total': 16}}), 'right')
        self.assertEqual(judge({'expect': 'count', 'truth': 16}, 200, {'status': 'answered', 'answer': {'total': 15}}), 'wrong')
        self.assertEqual(judge({'expect': 'sum', 'truth': 2426560}, 200, {'status': 'answered', 'answer': {'measure': {'value': 2426560}}}), 'right')
        self.assertEqual(judge({'expect': 'sum', 'truth': 2426560}, 200, {'status': 'answered', 'answer': {'total': 144}}), 'wrong')   # no sum where one was asked
        top = {'expect': 'groups', 'truth': [['甲', 100], ['乙', 50]]}
        self.assertEqual(judge(top, 200, {'status': 'answered', 'answer': {'groups': [['甲', 100, 1], ['乙', 50, 2], ['丙', 1, 1]]}}), 'right')
        self.assertEqual(judge(top, 200, {'status': 'answered', 'answer': {'groups': [['乙', 50, 2], ['甲', 100, 1]]}}), 'wrong')
        self.assertEqual(judge(top, 200, {'status': 'answered', 'answer': {'groups': [['甲', 100, 1]]}}), 'wrong')   # fewer than asked

    def test_a_refusal_is_a_miss_unless_a_refusal_was_expected_and_an_error_is_its_own_word(self):
        self.assertEqual(judge({'expect': 'count', 'truth': 16}, 200, {'status': 'ontology_gap'}), 'missed')
        self.assertEqual(judge({'expect': 'refuse'}, 200, {'status': 'refused'}), 'right')
        self.assertEqual(judge({'expect': 'refuse'}, 200, {'status': 'answered', 'answer': {'total': 16}}), 'wrong')
        self.assertEqual(judge({'expect': 'count', 'truth': 16}, 502, {'error': '模型没有返回问题列表'}), 'error')
        self.assertEqual(judge({'expect': 'count', 'truth': 16}, None, None), 'error')


if __name__ == '__main__':
    unittest.main()

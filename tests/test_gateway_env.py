"""Which model endpoint the service talks to, from the environment: DeepSeek's own API with DEEPSEEK_API_KEY (as before), OpenRouter with
OPENROUTER_API_KEY (DeepSeek V4.1 Flash by default), and the operator's own base and model name over either."""
import unittest
from unittest import mock

from ontology_poc_generator.ontology_server import gateway_from_env, model_setting_problem


def gateway(env):
    with mock.patch.dict('os.environ', env, clear=True):
        return gateway_from_env()


class GatewayFromEnvTests(unittest.TestCase):
    def test_a_deepseek_key_talks_to_deepseek_as_before(self):
        made = gateway({'DEEPSEEK_API_KEY': 'k'})
        self.assertEqual((made._api_base, made.model), ('https://api.deepseek.com', 'deepseek-flash'))

    def test_an_openrouter_key_talks_to_openrouter_with_deepseek_v4_1_flash(self):
        made = gateway({'OPENROUTER_API_KEY': 'k'})
        self.assertEqual((made._api_base, made.model), ('https://openrouter.ai/api/v1', 'deepseek/deepseek-v4.1-flash'))

    def test_the_operator_may_name_the_base_and_the_model(self):
        made = gateway({'OPENROUTER_API_KEY': 'k', 'EIP_MODEL_API_BASE': 'https://example.test/v1/', 'EIP_MODEL_NAME': 'deepseek/deepseek-v4-pro'})
        self.assertEqual((made._api_base, made.model), ('https://example.test/v1', 'deepseek/deepseek-v4-pro'))

    def test_a_deepseek_key_wins_when_both_are_set_and_no_key_means_no_model(self):
        self.assertEqual(gateway({'DEEPSEEK_API_KEY': 'a', 'OPENROUTER_API_KEY': 'b'})._api_base, 'https://api.deepseek.com')
        self.assertIsNone(gateway({}))


class ModelSettingTests(unittest.TestCase):
    def test_a_deepseek_model_name_with_only_an_openrouter_key_is_named_at_start(self):
        with mock.patch.dict('os.environ', {'OPENROUTER_API_KEY': 'k', 'EIP_MODEL_NAME': 'deepseek-flash'}, clear=True):
            said = model_setting_problem()
        self.assertIn('deepseek-flash', said)
        self.assertIn('deepseek/deepseek-v4.1-flash', said)   # what an OpenRouter name looks like
        for env in ({'OPENROUTER_API_KEY': 'k'}, {'OPENROUTER_API_KEY': 'k', 'EIP_MODEL_NAME': 'deepseek/deepseek-v4-pro'},
                    {'DEEPSEEK_API_KEY': 'k', 'EIP_MODEL_NAME': 'deepseek-flash'}, {}):
            with self.subTest(env=env), mock.patch.dict('os.environ', env, clear=True):
                self.assertIsNone(model_setting_problem())

if __name__ == '__main__':
    unittest.main()

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ontology_poc_generator.recognition import ModelCompletion
from ontology_poc_generator.recognition_cli import build_parser, main


def candidate_content() -> str:
    return json.dumps(
        {
            "schema": "scenario_recognition_candidate.v1",
            "profile": "order_priority_intervention",
            "industry": "制造业供应链",
            "scene_name": "订单履约异常识别",
            "business_decision": "哪些订单进入优先干预队列",
            "decision_owner": "供应链计划经理",
            "trigger": "交期或物料齐套异常时",
            "participants": ["订单经理"],
            "additional_objects": ["订单行"],
            "constraints": ["ERP 是交易事实权威"],
            "data_sources": [],
            "desired_actions": ["创建人工核查任务"],
            "acceptance_questions": ["能否解释候选队列依据？"],
            "notes": "只读演示",
        },
        ensure_ascii=False,
    )


class FakeGateway:
    instances: list["FakeGateway"] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.__class__.instances.append(self)

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> ModelCompletion:
        return ModelCompletion("openai_compatible", "served-model", candidate_content())


class RecognitionCliTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeGateway.instances.clear()

    def test_parser_does_not_accept_api_key_value(self) -> None:
        option_strings = {
            option
            for action in build_parser()._actions
            for option in action.option_strings
        }
        self.assertNotIn("--api-key", option_strings)
        self.assertIn("--api-key-env", option_strings)

    def test_cli_runs_model_and_writes_complete_closed_demo_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scenario.txt"
            output = root / "demo.json"
            source.write_text("订单预计延期，需要识别人工干预场景。", encoding="utf-8")
            environment = {
                "DEMO_MODEL_KEY": "secret-value",
                "EIP_MODEL_API_BASE": "https://models.example/v1",
                "EIP_MODEL_NAME": "configured-model",
            }

            with patch.dict(os.environ, environment, clear=False), patch(
                "ontology_poc_generator.recognition_cli.OpenAICompatibleGateway",
                FakeGateway,
            ):
                exit_code = main(
                    [str(source), "--api-key-env", "DEMO_MODEL_KEY", "--output", str(output)]
                )

            self.assertEqual(exit_code, 0)
            envelope = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(envelope["schema"], "model_recognition_demo.v1")
            self.assertEqual(envelope["recognition"]["model"], "served-model")
            self.assertEqual(envelope["scenario"]["decision_key"], "order_priority_intervention")
            self.assertFalse(envelope["scenario"]["customer_data_available"])
            self.assertEqual(envelope["ontology_spec"]["compilation_status"], "complete")
            self.assertTrue(envelope["ontology_spec"]["reference_closure"]["is_closed"])
            self.assertEqual(FakeGateway.instances[0].kwargs["api_key"], "secret-value")
            self.assertNotIn("secret-value", output.read_text(encoding="utf-8"))
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_missing_model_configuration_is_input_error_without_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scenario.txt"
            output = root / "demo.json"
            source.write_text("订单异常", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=True):
                exit_code = main([str(source), "--output", str(output)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(output.exists())

    def test_output_failure_returns_three_and_leaves_no_partial_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scenario.txt"
            output = root / "demo.json"
            source.write_text("订单异常", encoding="utf-8")
            environment = {
                "EIP_MODEL_API_KEY": "secret-value",
                "EIP_MODEL_API_BASE": "https://models.example/v1",
                "EIP_MODEL_NAME": "configured-model",
            }
            with patch.dict(os.environ, environment, clear=True), patch(
                "ontology_poc_generator.recognition_cli.OpenAICompatibleGateway",
                FakeGateway,
            ), patch("ontology_poc_generator.recognition_cli.os.replace", side_effect=OSError("no space")):
                exit_code = main([str(source), "--output", str(output)])

            self.assertEqual(exit_code, 3)
            self.assertFalse(output.exists())
            self.assertEqual(list(root.glob(".*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

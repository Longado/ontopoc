import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ontology_poc_generator.agent_modeling_cli import build_parser, main
from ontology_poc_generator.recognition import ModelCompletion
from tests.test_agent_modeling import SOURCE_TEXT, decision_contract, ontology_proposal


class FakeGateway:
    instances: list["FakeGateway"] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.__class__.instances.append(self)

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> ModelCompletion:
        if self is self.__class__.instances[0]:
            payload = decision_contract()
            model = "decision-model"
        elif self is self.__class__.instances[1]:
            payload = ontology_proposal()
            model = "ontology-model"
        else:
            request = json.loads(user_prompt)
            verdicts = [
                {
                    "candidate_id": item["candidate_id"],
                    "verdict": "accept",
                    "reason": "原文直接支持",
                }
                for item in request["review_items"]
            ]
            payload = {
                "schema": "modeling_evidence_review.v1",
                "verdicts": verdicts,
            }
            model = "reviewer-model"
        return ModelCompletion(
            provider="openai_compatible",
            model=model,
            content=json.dumps(payload, ensure_ascii=False),
        )


class AgentModelingCliTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeGateway.instances.clear()

    def test_parser_reads_api_key_only_from_environment(self) -> None:
        option_strings = {
            option
            for action in build_parser()._actions
            for option in action.option_strings
        }
        self.assertNotIn("--api-key", option_strings)
        self.assertIn("--api-key-env", option_strings)

    def test_cli_runs_three_roles_and_writes_compiled_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "quality-event.txt"
            output = root / "model.json"
            source.write_text(SOURCE_TEXT, encoding="utf-8")
            environment = {
                "DEMO_MODEL_KEY": "secret-value",
                "EIP_MODEL_API_BASE": "https://models.example/v1",
                "EIP_MODEL_NAME": "configured-model",
            }

            with patch.dict(os.environ, environment, clear=True), patch(
                "ontology_poc_generator.agent_modeling_cli.OpenAICompatibleGateway",
                FakeGateway,
            ):
                exit_code = main(
                    [
                        str(source),
                        "--api-key-env",
                        "DEMO_MODEL_KEY",
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(exit_code, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["schema"], "multi_agent_modeling.v2")
            self.assertEqual(
                result["modeling_status"], "ready_for_human_confirmation"
            )
            self.assertEqual(
                [agent["role"] for agent in result["agents"]],
                ["decision_analyst", "ontology_modeler", "evidence_reviewer"],
            )
            self.assertEqual(result["decision_pack"]["pack"]["schema"], "decision_pack.v1")
            self.assertTrue(result["ontology_spec"]["reference_closure"]["is_closed"])
            self.assertTrue(result["boundaries"]["human_confirmation_required"])
            self.assertEqual(len(FakeGateway.instances), 3)
            self.assertEqual(FakeGateway.instances[0].kwargs["api_key"], "secret-value")
            self.assertNotIn("secret-value", output.read_text(encoding="utf-8"))
            self.assertEqual(list(root.glob(".*.tmp")), [])

    def test_missing_model_configuration_returns_input_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "quality-event.txt"
            output = root / "model.json"
            source.write_text("质量事件 QI-017", encoding="utf-8")

            with patch.dict(os.environ, {}, clear=True):
                exit_code = main([str(source), "--output", str(output)])

            self.assertEqual(exit_code, 2)
            self.assertFalse(output.exists())

    def test_output_cannot_overwrite_input(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "quality-event.txt"
            source.write_text("质量事件 QI-017", encoding="utf-8")

            exit_code = main([str(source), "--output", str(source)])

            self.assertEqual(exit_code, 3)
            self.assertEqual(source.read_text(encoding="utf-8"), "质量事件 QI-017")


if __name__ == "__main__":
    unittest.main()

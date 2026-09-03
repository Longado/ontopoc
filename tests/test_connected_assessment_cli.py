import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from ontology_poc_generator.recognition import ModelCompletion
from tests.test_agent_modeling import ReviewingGateway
from tests.test_connected_assessment import (
    AdvisoryGateway,
    MANIFEST,
    connected_decision_contract,
    connected_ontology_proposal,
)


class FakeGateway:
    instances: list["FakeGateway"] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.calls: list[tuple[str, str]] = []
        self.__class__.instances.append(self)

    def complete_json(self, *, system_prompt: str, user_prompt: str) -> ModelCompletion:
        self.calls.append((system_prompt, user_prompt))
        position = self.__class__.instances.index(self)
        if position == 0:
            payload = connected_decision_contract()
        elif position == 1:
            payload = connected_ontology_proposal()
        elif position == 2:
            request = json.loads(user_prompt)
            payload = {
                "schema": "modeling_evidence_review.v1",
                "verdicts": ReviewingGateway._accept_all(request),
            }
        else:
            gateway = AdvisoryGateway()
            return gateway.complete_json(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )
        return ModelCompletion(
            provider="openai_compatible",
            model=f"served-model-{position + 1}",
            content=json.dumps(payload, ensure_ascii=False),
        )


class ConnectedAssessmentCliTest(unittest.TestCase):
    def setUp(self) -> None:
        FakeGateway.instances.clear()

    def test_cli_runs_the_complete_read_only_assessment_and_writes_no_secret(self):
        from ontology_poc_generator.connected_assessment_cli import main

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "assessment.json"
            environment = {
                "EIP_MODEL_API_BASE": "https://models.example/v1",
                "EIP_MODEL_NAME": "configured-model",
                "EIP_MODEL_API_KEY": "secret-model-key",
            }
            with patch.dict(os.environ, environment, clear=True), patch(
                "ontology_poc_generator.connected_assessment_cli.OpenAICompatibleGateway",
                FakeGateway,
            ):
                exit_code = main([str(MANIFEST), "--output", str(output)])

            self.assertEqual(exit_code, 0)
            result = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(result["schema"], "connected_quality_assessment.v1")
            self.assertEqual(result["assessment_status"], "ready_for_human_confirmation")
            self.assertEqual(len(FakeGateway.instances), 4)
            self.assertNotIn("secret-model-key", output.read_text(encoding="utf-8"))
            self.assertFalse(result["boundaries"]["external_action_executed"])

    def test_cli_cannot_overwrite_a_local_source_file(self):
        from ontology_poc_generator.connected_assessment_cli import main

        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for item in manifest["sources"]:
                content = (MANIFEST.parent / item["location"]).read_bytes()
                (root / item["location"]).write_bytes(content)
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            erp_path = root / "erp.json"
            original = erp_path.read_bytes()
            environment = {
                "EIP_MODEL_API_BASE": "https://models.example/v1",
                "EIP_MODEL_NAME": "configured-model",
                "EIP_MODEL_API_KEY": "secret-model-key",
            }

            with patch.dict(os.environ, environment, clear=True), patch(
                "ontology_poc_generator.connected_assessment_cli.OpenAICompatibleGateway",
                FakeGateway,
            ):
                exit_code = main(
                    [str(manifest_path), "--output", str(erp_path)]
                )

            self.assertEqual(exit_code, 3)
            self.assertEqual(erp_path.read_bytes(), original)
            self.assertEqual(FakeGateway.instances, [])


if __name__ == "__main__":
    unittest.main()

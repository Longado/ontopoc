import io
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch

from ontology_poc_generator.recognition_cli import main


class RecognitionCliSafetyTest(unittest.TestCase):
    def test_invalid_model_url_is_input_error_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "scenario.txt"
            source.write_text("订单异常", encoding="utf-8")
            stderr = io.StringIO()

            with patch.dict(
                os.environ,
                {"EIP_MODEL_API_KEY": "secret-value"},
                clear=True,
            ), redirect_stderr(stderr):
                exit_code = main(
                    [
                        str(source),
                        "--api-base",
                        "https://models.example/invalid\npath",
                        "--model",
                        "configured-model",
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("input error: model request failed", stderr.getvalue())
            self.assertNotIn("Traceback", stderr.getvalue())

    def test_output_resolving_to_input_is_rejected_before_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scenario.txt"
            output_alias = root / "demo.json"
            original = "订单异常，需要识别干预场景。".encode("utf-8")
            source.write_bytes(original)
            output_alias.symlink_to(source)

            with patch.dict(
                os.environ,
                {
                    "EIP_MODEL_API_KEY": "secret-value",
                    "EIP_MODEL_API_BASE": "https://models.example/v1",
                    "EIP_MODEL_NAME": "configured-model",
                },
                clear=True,
            ), patch(
                "ontology_poc_generator.recognition_cli.OpenAICompatibleGateway",
                side_effect=AssertionError("model must not be called"),
            ):
                exit_code = main([str(source), "--output", str(output_alias)])

            self.assertEqual(exit_code, 3)
            self.assertEqual(source.read_bytes(), original)
            self.assertTrue(output_alias.is_symlink())

    def test_case_aliased_knowledge_output_is_rejected_before_model_call(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "scenario.txt"
            knowledge = root / "Policy.JSON"
            output = root / "policy.json"
            source.write_text("订单异常", encoding="utf-8")
            original = b"preserve these knowledge bytes"
            knowledge.write_bytes(original)

            with patch.dict(
                os.environ,
                {
                    "EIP_MODEL_API_KEY": "secret-value",
                    "EIP_MODEL_API_BASE": "https://models.example/v1",
                    "EIP_MODEL_NAME": "configured-model",
                },
                clear=True,
            ), patch(
                "ontology_poc_generator.recognition_cli.OpenAICompatibleGateway",
                side_effect=AssertionError("model must not be called"),
            ):
                exit_code = main(
                    [
                        str(source),
                        "--knowledge-unit",
                        str(knowledge),
                        "--output",
                        str(output),
                    ]
                )

            self.assertEqual(exit_code, 3)
            self.assertEqual(knowledge.read_bytes(), original)
            if output.exists():
                self.assertTrue(output.samefile(knowledge))
                self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class CliTest(unittest.TestCase):
    def test_cli_generates_markdown_file(self):
        scenario = {
            "industry": "供应链",
            "scene_name": "订单履约风险处置",
            "business_decision": "选择需要优先处置的订单",
            "decision_owner": "计划经理",
            "trigger": "订单存在延期风险时",
            "objects": ["订单", "物料", "供应商"],
            "acceptance_questions": ["能否解释处置优先级？"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = root / "scenario.json"
            output_path = root / "proposal.md"
            input_path.write_text(json.dumps(scenario, ensure_ascii=False), encoding="utf-8")
            env = {**os.environ, "PYTHONPATH": "src"}

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "ontology_poc_generator.cli",
                    str(input_path),
                    "--output",
                    str(output_path),
                ],
                cwd=Path(__file__).parents[1],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("订单履约风险处置", output_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

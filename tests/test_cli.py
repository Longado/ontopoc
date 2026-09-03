import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from ontology_poc_generator.cli import _stage_output, build_parser, main
from ontology_poc_generator.compiler import compile_decision_pack
from ontology_poc_generator.decision_pack import render_decision_pack_json
from ontology_poc_generator.errors import SpecCompilationError
from ontology_poc_generator.knowledge import load_knowledge_unit
from ontology_poc_generator.models import ScenarioParameters


class CliTest(unittest.TestCase):
    REPO_ROOT = Path(__file__).parents[1]
    KNOWLEDGE_PATH = (
        REPO_ROOT
        / "knowledge/supply_chain/supplier_evidence_boundary_v1.json"
    )
    POLICY_PATH = (
        REPO_ROOT
        / "knowledge/supply_chain/order_priority_policy_synthetic_s1_v1.json"
    )

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "ontology_poc_generator.cli", *args],
            cwd=self.REPO_ROOT,
            env={**os.environ, "PYTHONPATH": "src"},
            text=True,
            capture_output=True,
            check=False,
        )

    def _run_main_with_second_replace_failure(
        self,
        proposal_output: Path,
        spec_output: Path,
        *,
        fail_rollback: bool = False,
    ) -> tuple[int, str]:
        original_replace = os.replace
        replace_count = 0

        def fail_second_replace(source: Path, target: Path) -> None:
            nonlocal replace_count
            replace_count += 1
            if replace_count == 2:
                raise OSError("second finalization failed")
            if fail_rollback and replace_count == 3:
                raise OSError("rollback restore failed")
            original_replace(source, target)

        stderr = StringIO()
        with patch(
            "ontology_poc_generator.cli.os.replace",
            side_effect=fail_second_replace,
        ), redirect_stderr(stderr):
            result = main(
                [
                    str(self.REPO_ROOT / "examples/supply_chain_exception.json"),
                    "--format",
                    "json",
                    "--output",
                    str(proposal_output),
                    "--ontology-spec-output",
                    str(spec_output),
                ]
            )
        return result, stderr.getvalue()

    def test_parser_accepts_repeatable_knowledge_units_in_argument_order(self):
        args = build_parser().parse_args(
            [
                "scenario.json",
                "--knowledge-unit",
                "first.json",
                "--knowledge-unit",
                "second.json",
            ]
        )

        self.assertEqual(
            args.knowledge_units,
            [Path("first.json"), Path("second.json")],
        )

    def test_parser_accepts_ontology_spec_output_path(self):
        args = build_parser().parse_args(
            ["scenario.json", "--ontology-spec-output", "ontology-spec.json"]
        )

        self.assertEqual(args.ontology_spec_output, Path("ontology-spec.json"))

    def test_parser_accepts_decision_pack_output_path(self):
        args = build_parser().parse_args(
            ["scenario.json", "--decision-pack-output", "decision-pack.json"]
        )

        self.assertEqual(args.decision_pack_output, Path("decision-pack.json"))

    def test_cli_writes_read_only_implementation_map_without_changing_spec(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            spec_output = root / "ontology-spec.json"
            map_output = root / "implementation-map.json"

            result = self._run_cli(
                "examples/supply_chain_exception.json",
                "--knowledge-unit",
                str(self.POLICY_PATH),
                "--ontology-spec-output",
                str(spec_output),
                "--implementation-map-output",
                str(map_output),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            spec_payload = json.loads(spec_output.read_text(encoding="utf-8"))
            map_payload = json.loads(map_output.read_text(encoding="utf-8"))
            self.assertNotIn("implementation_map", spec_payload)
            self.assertEqual(map_payload["schema"], "implementation_map.v1")
            self.assertIs(map_payload["editable"], False)
            self.assertEqual(
                map_payload["ontology_spec_content_hash"],
                spec_payload["spec_content_hash"],
            )
            rule = next(
                item
                for item in map_payload["entries"]
                if item["element_kind"] == "rule_declaration"
            )
            self.assertEqual(rule["execution_state"], "runtime_executable")
            self.assertEqual(
                rule["source_ref_ids"],
                ["synthetic_order_priority_policy_cases_v1"],
            )

    def test_omitting_ontology_spec_output_preserves_fixed_proposal_bytes(self):
        cases = (
            (
                (),
                "2c8fdbee13e3233b2d714b4c663998da7b7313014e887f8b8d1092671c49c50f",
            ),
            (
                ("--format", "json"),
                "d848ca2121501dfc943b5f81b44e72624a003d11a0e3174deed5d2c2a581b5a6",
            ),
        )
        for extra_args, expected_sha256 in cases:
            with self.subTest(extra_args=extra_args):
                result = self._run_cli(
                    "examples/supply_chain_exception.json",
                    *extra_args,
                )

                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                self.assertEqual(
                    hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
                    expected_sha256,
                )

    def test_cli_writes_deterministic_draft_ontology_spec_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first_output = root / "first-ontology-spec.json"
            second_output = root / "second-ontology-spec.json"
            common = (
                "examples/supply_chain_exception.json",
                "--knowledge-unit",
                str(self.KNOWLEDGE_PATH),
                "--format",
                "json",
            )

            first = self._run_cli(
                *common,
                "--ontology-spec-output",
                str(first_output),
            )
            second = self._run_cli(
                *common,
                "--ontology-spec-output",
                str(second_output),
            )

            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first_output.read_bytes(), second_output.read_bytes())
            payload = json.loads(first_output.read_text(encoding="utf-8"))
            self.assertEqual(
                tuple(payload),
                (
                    "compilation_status",
                    "reference_closure",
                    "spec",
                    "spec_content_hash",
                ),
            )
            self.assertEqual(payload["spec"]["schema"], "ontology_spec.v1")
            self.assertEqual(payload["spec"]["stage"], "draft")
            self.assertEqual(payload["spec"]["evidence_scope"], "synthetic_demo")
            self.assertEqual(payload["spec"]["governance_status"], "candidate")
            self.assertRegex(payload["spec_content_hash"], r"^[0-9a-f]{64}$")
            self.assertEqual(payload["compilation_status"], "complete")
            closure = payload["reference_closure"]
            self.assertEqual(
                tuple(closure),
                ("checked_reference_count", "is_closed", "issues"),
            )
            self.assertTrue(closure["is_closed"])
            self.assertGreater(closure["checked_reference_count"], 0)
            self.assertEqual(closure["issues"], [])
            self.assertFalse(
                any(
                    issue["severity"] == "blocking"
                    for issue in payload["spec"]["compilation_issues"]
                )
            )

    def test_cli_writes_canonical_decision_pack_instead_of_proposal_projection(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "decision-pack.json"

            result = self._run_cli(
                "examples/supply_chain_exception.json",
                "--knowledge-unit",
                str(self.KNOWLEDGE_PATH),
                "--format",
                "json",
                "--decision-pack-output",
                str(output_path),
            )

            raw_scenario = json.loads(
                (self.REPO_ROOT / "examples/supply_chain_exception.json").read_text(
                    encoding="utf-8"
                )
            )
            expected_pack = compile_decision_pack(
                ScenarioParameters.from_dict(raw_scenario),
                (load_knowledge_unit(self.KNOWLEDGE_PATH),),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                output_path.read_text(encoding="utf-8"),
                render_decision_pack_json(expected_pack),
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema"], "decision_pack.v1")
            self.assertIn("input_bindings", payload)
            self.assertIn("source_refs", payload)
            self.assertIn("knowledge_outcomes", payload)
            self.assertNotIn("primary_decision", payload)

    def test_spec_compilation_failure_is_an_input_error_without_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_output = root / "proposal.json"
            spec_output = root / "ontology-spec.json"
            stderr = StringIO()

            with patch(
                "ontology_poc_generator.cli.compile_ontology_spec",
                side_effect=SpecCompilationError("fatal", "cannot compile"),
            ), redirect_stderr(stderr):
                result = main(
                    [
                        "examples/supply_chain_exception.json",
                        "--format",
                        "json",
                        "--output",
                        str(proposal_output),
                        "--ontology-spec-output",
                        str(spec_output),
                    ]
                )

            self.assertEqual(result, 2)
            self.assertIn("input error: cannot compile", stderr.getvalue())
            self.assertFalse(proposal_output.exists())
            self.assertFalse(spec_output.exists())

    def test_cli_rejects_identical_proposal_and_spec_output_without_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared_output = root / "shared.json"

            result = self._run_cli(
                "examples/supply_chain_exception.json",
                "--format",
                "json",
                "--output",
                str(shared_output),
                "--ontology-spec-output",
                str(shared_output),
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("output error:", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(list(root.iterdir()), [])

    def test_cli_rejects_aliased_outputs_without_changing_existing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            alias_parent = root / "alias-parent"
            alias_parent.mkdir()
            shared_output = root / "shared.json"
            original = b"original output\n"
            shared_output.write_bytes(original)

            result = self._run_cli(
                "examples/supply_chain_exception.json",
                "--format",
                "json",
                "--output",
                str(shared_output),
                "--ontology-spec-output",
                str(alias_parent / ".." / shared_output.name),
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("output error:", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(shared_output.read_bytes(), original)
            self.assertEqual(
                sorted(path.name for path in root.iterdir()),
                ["alias-parent", "shared.json"],
            )
            self.assertEqual(list(root.glob(".*.tmp")), [])
            self.assertEqual(list(root.glob(".*.bak")), [])

    def test_cli_rejects_case_aliased_outputs_without_changing_existing_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_output = root / "Artifact.json"
            spec_output = root / "artifact.json"
            original = b"original output\n"
            proposal_output.write_bytes(original)

            result = self._run_cli(
                "examples/supply_chain_exception.json",
                "--format",
                "json",
                "--output",
                str(proposal_output),
                "--ontology-spec-output",
                str(spec_output),
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("output error:", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(proposal_output.read_bytes(), original)
            self.assertEqual(
                sorted(path.name for path in root.iterdir()),
                ["Artifact.json"],
            )
            self.assertEqual(list(root.glob(".*.tmp")), [])
            self.assertEqual(list(root.glob(".*.bak")), [])

    def test_cli_rejects_decision_pack_collision_with_any_other_output(self):
        cases = (
            ("--output", "proposal.json"),
            ("--ontology-spec-output", "ontology-spec.json"),
        )
        for other_flag, other_name in cases:
            with self.subTest(other_flag=other_flag):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    other_output = root / other_name
                    decision_output = root / other_name.upper()
                    original = b"original output\n"
                    other_output.write_bytes(original)

                    result = self._run_cli(
                        "examples/supply_chain_exception.json",
                        "--format",
                        "json",
                        other_flag,
                        str(other_output),
                        "--decision-pack-output",
                        str(decision_output),
                    )

                    self.assertEqual(result.returncode, 3)
                    self.assertIn("output error:", result.stderr)
                    self.assertEqual(result.stdout, "")
                    self.assertEqual(other_output.read_bytes(), original)
                    self.assertEqual(list(root.glob(".*.tmp")), [])
                    self.assertEqual(list(root.glob(".*.bak")), [])

    def test_failed_decision_pack_staging_leaves_no_other_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_output = root / "proposal.json"
            spec_output = root / "ontology-spec.json"

            result = self._run_cli(
                "examples/supply_chain_exception.json",
                "--format",
                "json",
                "--output",
                str(proposal_output),
                "--ontology-spec-output",
                str(spec_output),
                "--decision-pack-output",
                "/dev/null/decision-pack.json",
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("output error:", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse(proposal_output.exists())
            self.assertFalse(spec_output.exists())
            self.assertEqual(list(root.iterdir()), [])

    def test_failed_spec_staging_leaves_no_new_proposal_or_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_output = root / "proposal.json"

            result = self._run_cli(
                "examples/supply_chain_exception.json",
                "--format",
                "json",
                "--output",
                str(proposal_output),
                "--ontology-spec-output",
                "/dev/null/ontology-spec.json",
            )

            self.assertEqual(result.returncode, 3)
            self.assertIn("output error:", result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertFalse(proposal_output.exists())
            self.assertEqual(list(root.iterdir()), [])

    def test_failed_temp_write_cleans_the_new_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output_path = root / "ontology-spec.json"

            with patch.object(Path, "write_text", side_effect=OSError("disk full")):
                with self.assertRaisesRegex(OSError, "disk full"):
                    _stage_output(output_path, "content")

            self.assertEqual(list(root.iterdir()), [])

    def test_second_finalization_failure_removes_newly_installed_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_output = root / "proposal.json"
            spec_output = root / "ontology-spec.json"

            result, stderr = self._run_main_with_second_replace_failure(
                proposal_output,
                spec_output,
            )

            self.assertEqual(result, 3)
            self.assertIn("output error: second finalization failed", stderr)
            self.assertFalse(proposal_output.exists())
            self.assertFalse(spec_output.exists())
            self.assertEqual(list(root.iterdir()), [])

    def test_second_finalization_failure_restores_preexisting_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_output = root / "proposal.json"
            spec_output = root / "ontology-spec.json"
            original_proposal = b"original proposal\n"
            original_spec = b'{"original":true}\n'
            proposal_output.write_bytes(original_proposal)
            spec_output.write_bytes(original_spec)

            result, stderr = self._run_main_with_second_replace_failure(
                proposal_output,
                spec_output,
            )

            self.assertEqual(result, 3)
            self.assertIn("output error: second finalization failed", stderr)
            self.assertEqual(proposal_output.read_bytes(), original_proposal)
            self.assertEqual(spec_output.read_bytes(), original_spec)
            self.assertEqual(
                sorted(path.name for path in root.iterdir()),
                ["ontology-spec.json", "proposal.json"],
            )

    def test_failed_restore_retains_recoverable_backup_of_original_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proposal_output = root / "proposal.json"
            spec_output = root / "ontology-spec.json"
            original_proposal = b"original proposal\n"
            original_spec = b'{"original":true}\n'
            proposal_output.write_bytes(original_proposal)
            spec_output.write_bytes(original_spec)

            result, stderr = self._run_main_with_second_replace_failure(
                proposal_output,
                spec_output,
                fail_rollback=True,
            )

            self.assertEqual(result, 3)
            self.assertIn("output error: second finalization failed", stderr)
            self.assertIn("rollback error: rollback restore failed", stderr)
            self.assertEqual(spec_output.read_bytes(), original_spec)
            backups = list(root.glob(".proposal.json.*.bak"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_bytes(), original_proposal)
            self.assertEqual(list(root.glob("*.tmp")), [])
            self.assertEqual(list(root.glob(".ontology-spec.json.*.bak")), [])

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

    def test_cli_does_not_load_knowledge_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "proposal.json"
            result = self._run_cli(
                "examples/supply_chain_exception.json",
                "--format",
                "json",
                "--output",
                str(output_path),
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertNotIn("input_bindings", rendered)
            self.assertNotIn("knowledge_source_refs", rendered)
            self.assertNotIn("knowledge_outcomes", rendered)

    def test_cli_projects_applicable_knowledge_to_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            json_output = root / "proposal.json"
            markdown_output = root / "proposal.md"
            common = (
                "examples/supply_chain_exception.json",
                "--knowledge-unit",
                str(self.KNOWLEDGE_PATH),
            )

            json_result = self._run_cli(
                *common,
                "--format",
                "json",
                "--output",
                str(json_output),
            )
            markdown_result = self._run_cli(
                *common,
                "--output",
                str(markdown_output),
            )

            self.assertEqual(json_result.returncode, 0, json_result.stderr)
            self.assertEqual(markdown_result.returncode, 0, markdown_result.stderr)
            rendered = json.loads(json_output.read_text(encoding="utf-8"))
            outcome = rendered["knowledge_outcomes"][0]
            self.assertEqual(outcome["match_status"], "applicable")
            self.assertEqual(len(outcome["suggestions"]), 7)
            self.assertEqual(
                outcome["suggestions"][0]["governance_status"],
                "candidate",
            )
            markdown = markdown_output.read_text(encoding="utf-8")
            self.assertIn("## 有来源的候选建议", markdown)
            self.assertIn("匹配状态：`applicable`", markdown)
            self.assertIn("synthetic_demo", markdown)

    def test_cli_input_failures_return_two_without_creating_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            invalid_json = root / "invalid.json"
            invalid_json.write_text("{", encoding="utf-8")
            invalid_contract = root / "invalid-contract.json"
            invalid_contract.write_text("{}", encoding="utf-8")
            invalid_encoding = root / "invalid-encoding.json"
            invalid_encoding.write_bytes(b"\xff\xfe")

            cases = (
                ("missing", root / "missing.json"),
                ("invalid", invalid_json),
                ("contract", invalid_contract),
                ("encoding", invalid_encoding),
            )
            for name, knowledge_path in cases:
                with self.subTest(name=name):
                    output_path = root / name / "proposal.json"
                    result = self._run_cli(
                        "examples/supply_chain_exception.json",
                        "--knowledge-unit",
                        str(knowledge_path),
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertIn("input error:", result.stderr)
                    self.assertFalse(output_path.exists())
                    self.assertFalse(output_path.parent.exists())

    def test_cli_rejects_non_object_or_non_utf8_scenario_without_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            array_input = root / "array.json"
            array_input.write_text("[]", encoding="utf-8")
            invalid_encoding = root / "invalid-encoding.json"
            invalid_encoding.write_bytes(b"\xff\xfe")

            for name, input_path in (
                ("array", array_input),
                ("encoding", invalid_encoding),
            ):
                with self.subTest(name=name):
                    output_path = root / name / "proposal.json"
                    result = self._run_cli(
                        str(input_path),
                        "--format",
                        "json",
                        "--output",
                        str(output_path),
                    )

                    self.assertEqual(result.returncode, 2)
                    self.assertIn("input error:", result.stderr)
                    self.assertFalse(output_path.exists())
                    self.assertFalse(output_path.parent.exists())

    def test_cli_reports_output_error_separately(self):
        output_path = Path("/dev/null/proposal.md")

        result = self._run_cli(
            "examples/supply_chain_exception.json",
            "--output",
            str(output_path),
        )

        self.assertEqual(result.returncode, 3)
        self.assertIn("output error:", result.stderr)
        self.assertNotIn("input error:", result.stderr)


if __name__ == "__main__":
    unittest.main()

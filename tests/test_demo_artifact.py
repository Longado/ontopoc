import hashlib
import io
import json
import os
import stat
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from scripts import generate_demo_artifact


ROOT = Path(__file__).parents[1]
CASES_PATH = (
    ROOT / "tests/fixtures/policy/order_priority_policy_synthetic_cases_v1.json"
)


def content_hash(value):
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def resolve_artifact_ref(artifact, reference):
    if not reference.startswith("#/"):
        raise AssertionError(f"unsupported artifact reference: {reference}")
    value = artifact
    for key in reference[2:].split("/"):
        value = value[key]
    return value


class DemoArtifactTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.expected_cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))[
            "cases"
        ]

    def test_build_includes_versioned_validation_run(self):
        build_artifact = getattr(generate_demo_artifact, "build_artifact", lambda: {})

        artifact = build_artifact()

        self.assertIn("validation_run", artifact)
        validation_run = artifact["validation_run"]
        self.assertEqual(validation_run["schema"], "validation_run.v1")
        self.assertEqual(
            set(validation_run),
            {"schema", "authority", "runtime", "run_status", "cases"},
        )
        self.assertEqual(
            validation_run["authority"]["evidence_scope"],
            "synthetic_demo",
        )
        self.assertEqual(validation_run["runtime"]["mode"], "recorded_deterministic")
        self.assertFalse(validation_run["runtime"]["network_access"])
        self.assertFalse(validation_run["runtime"]["external_writes"])
        self.assertEqual(
            validation_run["run_status"],
            {
                "validation": "completed",
                "review": "not_started",
                "publication": "not_started",
                "action": "not_started",
                "external_write": False,
            },
        )

    def test_validation_run_contains_eight_real_bound_receipts(self):
        artifact = generate_demo_artifact.build_artifact()
        validation_run = artifact["validation_run"]
        authority = validation_run["authority"]
        actual_cases = validation_run["cases"]

        self.assertEqual(len(actual_cases), 4)
        baseline = authority["baseline"]
        self.assertEqual(
            baseline["decision_pack"],
            {
                "artifact_ref": "#/decision_pack",
                "content_hash": artifact["decision_pack"]["content_hash"],
            },
        )
        self.assertEqual(
            baseline["ontology_spec"],
            {
                "artifact_ref": "#/ontology_spec",
                "content_hash": artifact["ontology_spec"]["content_hash"],
            },
        )

        receipt_count = 0
        for expected_case, actual_case in zip(
            self.expected_cases,
            actual_cases,
            strict=True,
        ):
            with self.subTest(subject_id=expected_case["subject_id"]):
                self.assertEqual(actual_case["subject_id"], expected_case["subject_id"])
                facts = actual_case["facts"]
                self.assertEqual(facts["fact_set"]["evidence_scope"], "synthetic_demo")
                self.assertEqual(facts["content_hash"], content_hash(facts["fact_set"]))

                for label in ("baseline", "candidate"):
                    receipt_count += 1
                    variant = authority[label]
                    receipt_envelope = actual_case[label]
                    receipt = receipt_envelope["receipt"]
                    expected = expected_case["expected"][label]

                    self.assertEqual(
                        receipt_envelope["content_hash"],
                        content_hash(receipt),
                    )
                    self.assertEqual(
                        receipt["evaluation_status"],
                        expected["evaluation_status"],
                    )
                    self.assertEqual(
                        receipt["decision_result"],
                        expected["conclusion_value"],
                    )
                    self.assertEqual(
                        receipt["decision_pack_content_hash"],
                        variant["decision_pack"]["content_hash"],
                    )
                    self.assertEqual(
                        receipt["ontology_spec_content_hash"],
                        variant["ontology_spec"]["content_hash"],
                    )
                    self.assertEqual(
                        receipt["facts_content_hash"],
                        facts["content_hash"],
                    )
                    decision_pack = variant["decision_pack"]
                    ontology_spec = variant["ontology_spec"]
                    if "artifact_ref" in decision_pack:
                        resolved_pack = resolve_artifact_ref(
                            artifact,
                            decision_pack["artifact_ref"],
                        )["pack"]
                        resolved_spec = resolve_artifact_ref(
                            artifact,
                            ontology_spec["artifact_ref"],
                        )["spec"]
                    else:
                        resolved_pack = decision_pack["pack"]
                        resolved_spec = ontology_spec["spec"]
                    self.assertEqual(
                        decision_pack["content_hash"],
                        content_hash(resolved_pack),
                    )
                    self.assertEqual(
                        ontology_spec["content_hash"],
                        content_hash(resolved_spec),
                    )
                    for field in (
                        "draft_created",
                        "published",
                        "actions_executed",
                        "external_write",
                    ):
                        self.assertIs(receipt[field], False)

        self.assertEqual(receipt_count, 8)

    def test_candidate_changes_only_at_risk_case_from_fail_to_pass(self):
        cases = generate_demo_artifact.build_artifact()["validation_run"]["cases"]
        at_risk = next(
            item for item in cases if item["subject_id"] == "order.synthetic.002"
        )

        self.assertEqual(at_risk["baseline"]["receipt"]["evaluation_status"], "fail")
        self.assertEqual(at_risk["candidate"]["receipt"]["evaluation_status"], "pass")
        self.assertNotEqual(
            at_risk["baseline"]["receipt"]["decision_pack_content_hash"],
            at_risk["candidate"]["receipt"]["decision_pack_content_hash"],
        )
        self.assertNotEqual(
            at_risk["baseline"]["receipt"]["ontology_spec_content_hash"],
            at_risk["candidate"]["receipt"]["ontology_spec_content_hash"],
        )

    def test_repeated_builds_are_byte_identical(self):
        first = generate_demo_artifact.canonical_artifact_bytes(
            generate_demo_artifact.build_artifact()
        )
        second = generate_demo_artifact.canonical_artifact_bytes(
            generate_demo_artifact.build_artifact()
        )

        self.assertEqual(first, second)

    def test_check_mode_matches_without_writing_and_rejects_stale_or_missing_file(self):
        expected = generate_demo_artifact.canonical_artifact_bytes(
            generate_demo_artifact.build_artifact()
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifact.json"
            output.write_bytes(expected)

            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = generate_demo_artifact.main(["--check"], output=output)
            self.assertEqual(result, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(stderr.getvalue(), "")
            self.assertEqual(output.read_bytes(), expected)

            output.write_bytes(b"stale artifact\n")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = generate_demo_artifact.main(["--check"], output=output)
            self.assertEqual(result, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(
                stderr.getvalue(),
                f"artifact is missing or stale: {output}\n",
            )
            self.assertEqual(output.read_bytes(), b"stale artifact\n")

            output.unlink()
            stdout = io.StringIO()
            stderr = io.StringIO()
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = generate_demo_artifact.main(["--check"], output=output)
            self.assertEqual(result, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(
                stderr.getvalue(),
                f"artifact is missing or stale: {output}\n",
            )
            self.assertFalse(output.exists())

    def test_default_write_uses_same_directory_replace(self):
        expected = generate_demo_artifact.canonical_artifact_bytes(
            generate_demo_artifact.build_artifact()
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifact.json"
            with mock.patch.object(
                generate_demo_artifact.os,
                "replace",
                wraps=os.replace,
            ) as replace:
                self.assertEqual(generate_demo_artifact.main([], output=output), 0)

            self.assertEqual(output.read_bytes(), expected)
            replace.assert_called_once()
            temporary, destination = map(Path, replace.call_args.args)
            self.assertEqual(temporary.parent, output.parent)
            self.assertEqual(destination, output)
            self.assertFalse(temporary.exists())
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o644)

    def test_replace_preserves_existing_public_artifact_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifact.json"
            output.write_bytes(b"previous artifact\n")
            output.chmod(0o644)

            generate_demo_artifact.write_artifact(output, b"new artifact\n")

            self.assertEqual(output.read_bytes(), b"new artifact\n")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o644)

    def test_replace_failure_preserves_existing_artifact_and_cleans_temp_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "artifact.json"
            output.write_bytes(b"previous artifact\n")
            output.chmod(0o644)

            with mock.patch.object(
                generate_demo_artifact.os,
                "replace",
                side_effect=OSError("replace failed"),
            ), self.assertRaisesRegex(OSError, "replace failed"):
                generate_demo_artifact.write_artifact(output, b"new artifact\n")

            self.assertEqual(output.read_bytes(), b"previous artifact\n")
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o644)
            self.assertEqual(list(output.parent.glob(f".{output.name}.*.tmp")), [])


if __name__ == "__main__":
    unittest.main()

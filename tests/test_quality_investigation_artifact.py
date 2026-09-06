import importlib
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
COMMITTED_ARTIFACT = (
    ROOT / "landing-page/public/artifacts/quality-investigation.json"
)


def generator_module():
    try:
        return importlib.import_module(
            "scripts.generate_quality_investigation_artifact"
        )
    except ModuleNotFoundError:
        raise AssertionError(
            "quality investigation artifact generator is not implemented"
        ) from None


class QualityInvestigationArtifactTest(unittest.TestCase):
    def test_artifact_projects_only_the_investigation_result_needed_by_the_demo(self):
        generator = generator_module()

        artifact = generator.build_artifact()

        self.assertEqual(
            set(artifact),
            {
                "schema",
                "evidence_scope",
                "source_snapshot_ref",
                "quality_signal_id",
                "control_scope_objects",
                "factors",
                "gaps",
                "root_cause_confirmed",
            },
        )
        self.assertEqual(artifact["schema"], "investigation_scope.v1")
        self.assertEqual(artifact["evidence_scope"], "synthetic_demo")
        self.assertEqual(
            [item["status"] for item in artifact["control_scope_objects"]],
            [
                "confirmed_impact",
                "confirmed_impact",
                "possible_impact",
                "excluded",
                "not_evaluable",
            ],
        )
        self.assertEqual(
            {item["object_type"] for item in artifact["control_scope_objects"]},
            {
                "inventory",
                "work_in_process",
                "pending_shipment",
                "in_transit",
                "customer_side",
            },
        )
        self.assertTrue(
            all(item["reason"] for item in artifact["control_scope_objects"])
        )
        self.assertEqual(
            [item["status"] for item in artifact["factors"]],
            ["priority", "priority", "weakened"],
        )
        self.assertEqual(len(artifact["gaps"]), 1)
        self.assertIs(artifact["root_cause_confirmed"], False)

    def test_committed_artifact_is_canonical_and_check_mode_never_writes(self):
        generator = generator_module()
        expected = generator.canonical_artifact_bytes(generator.build_artifact())

        self.assertEqual(COMMITTED_ARTIFACT.read_bytes(), expected)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "quality-investigation.json"
            output.write_bytes(expected)
            self.assertEqual(generator.main(["--check"], output=output), 0)
            self.assertEqual(output.read_bytes(), expected)

            output.write_bytes(b"stale\n")
            self.assertEqual(generator.main(["--check"], output=output), 1)
            self.assertEqual(output.read_bytes(), b"stale\n")


if __name__ == "__main__":
    unittest.main()

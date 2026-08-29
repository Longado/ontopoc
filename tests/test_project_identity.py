from pathlib import Path
import tomllib
import unittest


PROJECT_FILE = Path(__file__).parents[1] / "pyproject.toml"


class ProjectIdentityTest(unittest.TestCase):
    def test_public_project_and_cli_names_are_ontopoc(self) -> None:
        project = tomllib.loads(PROJECT_FILE.read_text(encoding="utf-8"))["project"]

        self.assertEqual(project["name"], "ontopoc")
        self.assertEqual(project["scripts"]["ontopoc"], "ontology_poc_generator.cli:main")
        self.assertEqual(
            project["scripts"]["ontopoc-recognize"],
            "ontology_poc_generator.recognition_cli:main",
        )

    def test_legacy_cli_names_remain_as_compatibility_aliases(self) -> None:
        scripts = tomllib.loads(PROJECT_FILE.read_text(encoding="utf-8"))["project"][
            "scripts"
        ]

        self.assertEqual(scripts["ontology-poc"], scripts["ontopoc"])
        self.assertEqual(
            scripts["ontology-poc-recognize"], scripts["ontopoc-recognize"]
        )


if __name__ == "__main__":
    unittest.main()

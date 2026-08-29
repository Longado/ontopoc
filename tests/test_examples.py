import json
import unittest
from pathlib import Path

from ontology_poc_generator.generator import generate_proposal
from ontology_poc_generator.models import ScenarioParameters
from ontology_poc_generator.renderers import render_markdown


class ExampleContractTest(unittest.TestCase):
    def test_examples_cover_at_least_two_industries_without_special_case_code(self):
        examples = sorted((Path(__file__).parents[1] / "examples").glob("*.json"))
        proposals = []
        for path in examples:
            raw = json.loads(path.read_text(encoding="utf-8"))
            proposal = generate_proposal(ScenarioParameters.from_dict(raw))
            self.assertIn("## 业务决策卡", render_markdown(proposal))
            proposals.append(proposal)

        self.assertGreaterEqual(len({proposal.industry for proposal in proposals}), 2)


if __name__ == "__main__":
    unittest.main()

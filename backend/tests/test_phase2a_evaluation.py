import json
from pathlib import Path

import pytest

from tests.test_phase2a_correctness import answer
from app.services.rag.answering import AnswerService

DATASET = json.loads((Path(__file__).parents[1] / "evaluation/phase2a_cases.json").read_text())


@pytest.mark.parametrize("case", DATASET["cases"], ids=lambda c: c["id"])
def test_engineering_evidence_acceptance(case):
    result = (AnswerService().answer(case["question"], []) if case["evidence"] is None
              else answer(case["provider_output"], case["evidence"], case["question"]))
    assert result.found is case["expected_found"]
    if not result.found:
        assert not result.citations

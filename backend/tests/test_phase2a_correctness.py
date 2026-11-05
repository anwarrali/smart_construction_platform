"""Phase 2A regression cases: no provider credentials or production resources."""
from types import SimpleNamespace
from uuid import uuid4

from app.services.agents import analyzers
from app.services.agents.contracts import AgentFinding, Certainty, Evidence
from app.services.agents.runtime import _fingerprint
from app.services.rag.answering import AnswerService
from app.services.rag.retrieval import RetrievedChunk
from app.services.rag.store import ChunkSource, ScoredChunk


class Context:
    def __init__(self, values):
        self.values = values

    def data(self, name, arguments=None):
        return self.values.get(name, {})


def narrative(delays, issues=None):
    return Context({
        "get_site_reports": {"reports": [{"id": "report"}]},
        "get_site_report": {"report": {"id": "report", "delays": delays, "issuesSummary": issues}},
    })


def answer(reply, content="Concrete grade C30.", question="What concrete grade is required?"):
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: SimpleNamespace(choices=[SimpleNamespace(
            message=SimpleNamespace(content=reply))]))))
    chunks = [RetrievedChunk(ScoredChunk(uuid4(), ChunkSource.from_document(uuid4()),
                                         1, 0, content, 1.0), "Structural specification")]
    return AnswerService(client=client).answer(question, chunks)


def test_negated_delay_is_not_a_fact():
    findings = analyzers.site_report_agent(narrative("No delay expected; work remains on programme."))
    assert not any(f.code == "SITE_REPORTED_DELAYS" for f in findings)


def test_delay_fields_are_read_independently():
    findings = analyzers.site_report_agent(narrative("None", "Concrete delivery delayed 3 days"))
    assert any(f.code == "SITE_REPORTED_DELAYS" for f in findings)


def test_unsupported_number_cannot_be_accepted():
    assert not answer("Concrete grade C90 [1].").found


def test_non_numeric_unsupported_claim_is_rejected():
    assert not answer("Concrete is approved for construction [1].").found


def test_invalid_citation_cannot_be_accepted():
    assert not answer("Concrete grade C30 [999].").found


def test_supported_quote_remains_usable():
    assert answer("Concrete grade C30 [1].").found


def test_omitted_negation_or_applicability_is_not_a_supported_excerpt():
    assert not answer("Approved [1].", "Not approved.").found
    assert not answer("Concrete grade C30 [1].", "Concrete grade C30 only for nonstructural blinding.").found


def test_invalid_structured_output_is_not_an_answer():
    assert not answer('{"claims": [{"quote": "C30", "citations": [999]}], "verified": true}').found


def test_selected_citation_markers_match_returned_citation_list():
    chunks = [RetrievedChunk(ScoredChunk(uuid4(), ChunkSource.from_document(uuid4()),
                                         1, 0, content, 1.0), title)
              for content,title in [("Cover is 40 mm.","Cover"),("Concrete grade C30.","Grade")]]
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs:
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Concrete grade C30 [2]."))]))))
    result=AnswerService(client=client).answer("What grade?",chunks)
    assert result.found and result.answer=="Concrete grade C30 [1]."
    assert len(result.citations)==1 and result.citations[0].title=="Grade"


def test_finding_identity_survives_evidence_growth_and_order():
    def finding(ids):
        return AgentFinding(code="SCHEDULE_TASKS_OVERDUE", certainty=Certainty.FACT,
                            severity="HIGH", confidence=1, title="Overdue work", description="Dates",
                            reason="Dates", recommended_action="Review", affected={"tasks": ids},
                            evidence=[Evidence("TASK", item, "Work") for item in ids])
    assert _fingerprint("schedule", "project", finding(["a", "b"])) == _fingerprint(
        "schedule", "project", finding(["b", "a", "c"]))

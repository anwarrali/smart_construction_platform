"""Which source a question is sent to, and — more importantly — when it is not.

The rule this suite exists to protect: routing may only take work *away* from
document retrieval when it is confident something better holds the answer.
Every question used to be embedded and searched against document vectors, so
an unrouted question must still behave exactly as it did. A router that
redirects on a guess is worse than no router at all.
"""

import pytest

from app.schemas.voice_analysis import VoiceQueryTopic
from app.services.knowledge_router import (
    KnowledgeSource,
    SourceAvailability,
    route_question,
)

EVERYTHING = SourceAvailability(documents=True, ifc=True, site_reports=True, structured=True)


def route(question, availability=EVERYTHING):
    return route_question(question, availability=availability)


# --- Structured data is preferred when it holds the answer ------------------

@pytest.mark.parametrize("question, topic", [
    ("what is the project progress?", VoiceQueryTopic.PROJECT_PROGRESS),
    ("how far along is the project", VoiceQueryTopic.PROJECT_PROGRESS),
    ("are there any open issues", VoiceQueryTopic.OPEN_ISSUES),
    ("which tasks are blocked", VoiceQueryTopic.BLOCKED_TASKS),
    ("what are the remaining tasks", VoiceQueryTopic.REMAINING_TASKS),
    ("show me the completed tasks", VoiceQueryTopic.COMPLETED_TASKS),
])
def test_a_project_data_question_never_reaches_the_document_vectors(question, topic):
    decision = route(question)
    assert decision.source is KnowledgeSource.PROJECT_STRUCTURED
    assert decision.topic is topic
    assert decision.needs_document_retrieval is False


def test_the_routed_topic_is_one_the_backend_can_already_answer():
    """Routing reuses `VoiceQueryTopic` rather than inventing a taxonomy."""
    decision = route("what is the project progress?")
    assert decision.topic in set(VoiceQueryTopic)


def test_arabic_project_questions_route_the_same_way():
    assert route("شو نسبة الإنجاز؟").source is KnowledgeSource.PROJECT_STRUCTURED
    assert route("شو المشاكل المفتوحة").source is KnowledgeSource.PROJECT_STRUCTURED


# --- Site reports -----------------------------------------------------------

def test_a_request_for_the_latest_site_report_goes_to_site_reports():
    decision = route("what did the latest site report say")
    assert decision.source is KnowledgeSource.SITE_REPORTS
    assert decision.topic is VoiceQueryTopic.LATEST_SITE_REPORT


def test_site_report_beats_the_generic_report_wording():
    # "report" alone would also match weaker rules; the specific phrase wins.
    assert route("آخر تقرير موقع").source is KnowledgeSource.SITE_REPORTS


# --- IFC --------------------------------------------------------------------

@pytest.mark.parametrize("question", [
    "what conflicts with this beam",
    "are there any clashes on level 2",
    "does the duct pass through the beam",
    "شو التعارض مع الجسر",
])
def test_a_model_question_goes_to_the_ifc_source(question):
    assert route(question).source is KnowledgeSource.IFC_MODEL


def test_ifc_wins_over_document_wording_when_the_question_is_about_a_clash():
    assert route("is there a clash shown on the drawing").source is KnowledgeSource.IFC_MODEL


# --- Documents --------------------------------------------------------------

@pytest.mark.parametrize("question", [
    "what does the specification say about concrete grade",
    "what is the retention percentage in the contract",
    "which clause covers liquidated damages",
    "ماذا تقول المواصفات عن الخرسانة",
])
def test_a_document_question_goes_to_document_retrieval(question):
    decision = route(question)
    assert decision.source is KnowledgeSource.DOCUMENTS
    assert decision.needs_document_retrieval is True


def test_asking_what_a_document_says_wins_even_when_a_task_is_named():
    """Wording beats subject: this asks about text, not about the task."""
    decision = route("what does the specification say about the blocked tasks")
    assert decision.source is KnowledgeSource.DOCUMENTS


# --- The safe direction -----------------------------------------------------

def test_an_unrecognised_question_still_reaches_document_retrieval():
    """The pre-routing behaviour, preserved for everything not confidently placed."""
    decision = route("retention percentage")
    assert decision.source is KnowledgeSource.DOCUMENTS
    assert decision.needs_document_retrieval is True
    assert decision.matched is None
    assert decision.confidence < 0.5


def test_an_empty_question_does_not_get_routed_away():
    decision = route("   ")
    assert decision.source is KnowledgeSource.DOCUMENTS
    assert decision.confidence == 0.0


def test_a_confident_route_says_which_phrase_decided_it():
    decision = route("what is the project progress?")
    assert decision.matched
    assert decision.matched in decision.reason
    assert decision.confidence >= 0.8


# --- A source is never invented ---------------------------------------------

def test_a_model_question_falls_back_when_the_project_has_no_ifc():
    without_ifc = SourceAvailability(documents=True, ifc=False, site_reports=True, structured=True)
    decision = route("what conflicts with this beam", without_ifc)
    assert decision.source is KnowledgeSource.DOCUMENTS
    assert "IFC_MODEL" in decision.unavailable


def test_a_site_report_question_falls_back_when_none_have_been_filed():
    without_reports = SourceAvailability(documents=True, ifc=True, site_reports=False, structured=True)
    decision = route("what did the latest site report say", without_reports)
    assert decision.source is KnowledgeSource.DOCUMENTS
    assert "SITE_REPORTS" in decision.unavailable


def test_an_unavailable_source_is_recorded_rather_than_silently_dropped():
    without_ifc = SourceAvailability(documents=True, ifc=False, site_reports=True, structured=True)
    assert route("any clashes", without_ifc).unavailable == ["IFC_MODEL"]


# --- Serialisation ----------------------------------------------------------

def test_a_decision_serialises_with_its_reason():
    payload = route("what is the project progress?").as_json()
    assert payload["source"] == "PROJECT_STRUCTURED"
    assert payload["topic"] == "PROJECT_PROGRESS"
    assert payload["matched"]
    assert payload["reason"]


def test_matching_is_whole_phrase_not_substring():
    # "progressive collapse" contains "progress" but is not a progress question.
    decision = route("what does the spec say about progressive collapse")
    assert decision.source is KnowledgeSource.DOCUMENTS

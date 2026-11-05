from dataclasses import replace
from datetime import datetime, timedelta, timezone
from threading import Barrier, Event, Thread
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from tests.test_agents_integration import db, world
from tests.test_job_runner import queue
from app.db.database import SessionLocal
from app.models.ifc import AIInsight
from app.models.document import Document
from app.models.enums import DocumentType, TaskStatus
from app.services.jobs import queue as jobs
from app.services.jobs.ownership import LeaseLost, execution_lease
from app.services.agents.runtime import run_agent, _store
from app.services.agents.registry import BY_NAME
from app.services.agents.contracts import AgentFinding, Certainty, Evidence
from app.services.insight_access import can_read_insight


def reclaim(db, queue):
    key = jobs.enqueue(db, "test.fence", queue=queue)
    db.commit()
    old = jobs.claim(db, worker="old", capacity=2, queue=queue)
    db.execute(text("UPDATE background_jobs SET heartbeat_at=now()-interval '1 hour' WHERE id=:id"), {"id": key})
    db.commit()
    assert jobs.reap(db, queue=queue, stale_after=1) == 1
    db.execute(text("UPDATE background_jobs SET run_after=now() WHERE id=:id"), {"id": key})
    db.commit()
    new = jobs.claim(db, worker="new", capacity=2, queue=queue)
    return old, new


@pytest.mark.parametrize("operation", ["succeed", "fail", "reject"])
def test_stale_settlement_cannot_touch_reclaimed_work(db, queue, operation):
    old, new = reclaim(db, queue)
    with pytest.raises(LeaseLost):
        getattr(jobs, operation)(db, old, *([] if operation == "succeed" else ["old failure"]))
    db.rollback()
    jobs.heartbeat(db, [old])
    row = db.execute(text("SELECT status, attempts, locked_by FROM background_jobs WHERE id=:id"), {"id": new.id}).one()
    assert tuple(row) == ("RUNNING", 2, "new")
    db.rollback()
    jobs.succeed(db, new)


def insight(project_id):
    return AIInsight(project_id=project_id, fingerprint=uuid4().hex, insight_type="FENCE_TEST",
                     category="AGENT_FINDING", severity="HIGH", confidence=.9,
                     title="Paused worker evidence", description="Fixture", reason="Fixture",
                     recommended_action="Review", source_engine="TEST", status="NEW")


def test_stale_nested_domain_session_cannot_publish_findings(db, world, queue):
    old, new = reclaim(db, queue)
    value = insight(world["project"].id)
    with execution_lease(old), SessionLocal() as domain:
        domain.add(value)
        with pytest.raises(LeaseLost):
            domain.commit()
        domain.rollback()
    assert db.query(AIInsight).filter(AIInsight.fingerprint == value.fingerprint).count() == 0
    db.rollback()
    jobs.succeed(db, new)


def test_expired_worker_cannot_renew_or_publish_even_before_reap(db, world, queue):
    key = jobs.enqueue(db, "test.fence", queue=queue)
    db.commit()
    job = jobs.claim(db, worker="old", capacity=1, queue=queue)
    db.execute(text("UPDATE background_jobs SET heartbeat_at=now()-interval '1 hour' WHERE id=:id"), {"id": key})
    db.commit()
    jobs.heartbeat(db, [job])
    with pytest.raises(LeaseLost):
        jobs.succeed(db, job)
    db.rollback()


def test_hard_publication_deadline_wins_over_live_heartbeat(db, queue, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "JOB_MAX_EXECUTION_SECONDS", 1)
    key = jobs.enqueue(db, "test.fence", queue=queue)
    db.commit()
    job = jobs.claim(db, worker="live", capacity=1, queue=queue)
    db.execute(text("UPDATE background_jobs SET started_at=now()-interval '10 seconds' WHERE id=:id"), {"id": key})
    db.commit()
    jobs.heartbeat(db, [job])
    with pytest.raises(LeaseLost):
        jobs.succeed(db, job)
    db.rollback()
    assert jobs.reap(db, queue=queue) == 1


def test_concurrent_claims_cannot_share_one_generation(db, queue):
    key = jobs.enqueue(db, "test.fence", queue=queue)
    db.commit()
    start = Barrier(3)
    results, errors = [], []
    def claim(name):
        try:
            with SessionLocal() as session:
                start.wait(timeout=5)
                results.append(jobs.claim(session,worker=name,capacity=2,queue=queue))
        except Exception as exc:
            errors.append(exc)
    workers = [Thread(target=claim,args=(name,)) for name in ["a","b"]]
    for worker in workers: worker.start()
    start.wait(timeout=5)
    for worker in workers: worker.join(timeout=10)
    assert not errors and all(not w.is_alive() for w in workers)
    assert sum(r is not None for r in results) == 1


def test_document_agent_uses_authorized_list_instead_of_invalid_search(db, world):
    doc = Document(project_id=world["project"].id, uploaded_by_id=world["manager"].id,
                   title="S102", document_type=DocumentType.SPECIFICATION, file_url="/unused")
    db.add(doc); db.commit()
    try:
        result = run_agent(db,user=world["manager"],project_id=world["project"].id,
                           name="document_consistency_agent",persist=False)
        assert result.ok
        assert result.tool_calls[0]["tool"] == "list_documents"
        assert result.tool_calls[0]["ok"]
        assert not any(f.code in {"NO_DOCUMENTS","NO_AUTHORIZED_DOCUMENTS","DOCUMENTS_UNAVAILABLE"} for f in result.findings)
    finally:
        db.delete(doc); db.commit()


def test_tool_failure_is_failed_analysis_not_no_documents(db, world, monkeypatch):
    from app.services.ai_tools.registry import BY_NAME as TOOLS
    def broken(*args): raise RuntimeError("fixture failure")
    monkeypatch.setitem(TOOLS,"list_documents",replace(TOOLS["list_documents"],handler=broken))
    result = run_agent(db,user=world["manager"],project_id=world["project"].id,
                       name="document_consistency_agent",persist=False)
    assert not result.ok and result.as_json()["completeness"] == "FAILED"
    assert result.error_code == "DATA_RETRIEVAL_FAILED"


def test_truncated_task_scan_is_explicitly_partial(db, world, monkeypatch):
    from app.services.ai_tools.registry import BY_NAME as TOOLS
    previous = TOOLS["get_tasks"]
    def truncated(*args):
        value=previous.handler(*args); value["total"]=201; return value
    monkeypatch.setitem(TOOLS,"get_tasks",replace(previous,handler=truncated))
    result=run_agent(db,user=world["manager"],project_id=world["project"].id,
                     name="schedule_risk_agent",persist=False)
    assert result.ok and result.completeness == "PARTIAL" and result.coverage_reasons


def test_high_promotion_retains_severity_and_repetition_is_rejected(db, world):
    from app.api.ai_intelligence import insight_to_issue
    from app.models.issue import Issue
    value=insight(world["project"].id); db.add(value); db.commit()
    result=insight_to_issue(world["project"].id,value.id,db,world["manager"])
    assert db.get(Issue,result["id"]).severity.value == "high"
    with pytest.raises(HTTPException) as exc:
        insight_to_issue(world["project"].id,value.id,db,world["manager"])
    assert exc.value.status_code == 409
    db.rollback()


def test_restricted_document_is_not_exposed_through_derived_insight(db, world):
    from tests.office_roles import with_office_role
    from app.models.rbac import Discipline, UserDiscipline
    from app.services.document_access import readable_document_ids
    member=world["site_engineer"]
    with_office_role(db,member,"senior_engineer")
    electrical=db.query(Discipline).filter(Discipline.code=="electrical").first()
    db.add(UserDiscipline(user_id=member.id,discipline_id=electrical.id))
    task=world["blocked"];task.discipline="structural"
    doc=Document(project_id=world["project"].id,uploaded_by_id=world["manager"].id,
                 task_id=task.id,title="Restricted structural requirement",file_url="/unused")
    db.add(doc);db.flush()
    finding=AgentFinding(code="PRIVATE_SOURCE",certainty=Certainty.DETECTED,severity="HIGH",confidence=.9,
                         title="Restricted C40 requirement",description="Private source text",reason="Source",
                         recommended_action="Review",evidence=[Evidence("DOCUMENT",str(doc.id),doc.title)])
    value=_store(db,BY_NAME["document_consistency_agent"],world["project"].id,finding);db.commit()
    try:
        assert doc.id not in readable_document_ids(db,member,world["project"].id)
        assert can_read_insight(db,world["manager"],value)
        assert not can_read_insight(db,member,value)
        assert not can_read_insight(db,world["outsider"],value)
    finally:
        db.delete(doc);db.commit()


def test_acknowledged_finding_reassesses_without_reopening_terminal_decision(db, world):
    f=AgentFinding(code="SCHEDULE_TASKS_OVERDUE",certainty=Certainty.FACT,severity="HIGH",confidence=1,
                   title="Overdue",description="Before",reason="Date",recommended_action="Review",
                   affected={"tasks":[str(world["overdue"].id)]},
                   evidence=[Evidence("TASK",str(world["overdue"].id),"Task")])
    value=_store(db,BY_NAME["schedule_risk_agent"],world["project"].id,f);db.commit()
    value.status="ACKNOWLEDGED";db.commit()
    updated=_store(db,BY_NAME["schedule_risk_agent"],world["project"].id,replace(f,description="New evidence"))
    db.commit();assert updated.id==value.id and updated.description=="New evidence"
    updated.status="RESOLVED";db.commit()
    again=_store(db,BY_NAME["schedule_risk_agent"],world["project"].id,replace(f,description="Recurrence"))
    assert again.status=="RESOLVED" and again.description=="New evidence"


def test_paused_worker_resumes_after_transfer_without_publishing(db, world, queue, monkeypatch):
    from app.services.jobs.handlers import JobKind, KINDS
    from app.services.jobs.runner import execute
    paused, resume = Event(), Event()
    outcome=[]
    project_id=world["project"].id
    fingerprint=uuid4().hex
    def handler(payload, attempt):
        paused.set()
        assert resume.wait(timeout=10)
        with SessionLocal() as domain:
            value=insight(project_id);value.fingerprint=fingerprint
            domain.add(value);domain.commit()
    monkeypatch.setitem(KINDS,"test.paused",JobKind("test.paused",handler))
    key=jobs.enqueue(db,"test.paused",queue=queue);db.commit()
    old=jobs.claim(db,worker="paused",capacity=1,queue=queue)
    thread=Thread(target=lambda:outcome.append(execute(old)));thread.start()
    assert paused.wait(timeout=5)
    try:
        db.execute(text("UPDATE background_jobs SET heartbeat_at=now()-interval '1 hour' WHERE id=:id"),{"id":key});db.commit()
        assert jobs.reap(db,queue=queue,stale_after=1)==1
        db.execute(text("UPDATE background_jobs SET run_after=now() WHERE id=:id"),{"id":key});db.commit()
        fresh=jobs.claim(db,worker="replacement",capacity=1,queue=queue)
    finally:
        resume.set();thread.join(timeout=10)
    assert not thread.is_alive() and outcome==["LEASE_LOST"]
    assert db.query(AIInsight).filter(AIInsight.fingerprint==fingerprint).count()==0
    db.rollback();jobs.succeed(db,fresh)


def _blocked_process(payload, attempt):
    import time
    time.sleep(60)


def test_isolated_handler_is_terminated_at_deadline(db, queue, monkeypatch):
    import time
    from app.services.jobs.runner import _run_isolated
    from app.core.config import settings
    monkeypatch.setattr(settings,"JOB_MAX_EXECUTION_SECONDS",1)
    key=jobs.enqueue(db,"test.timeout",queue=queue);db.commit()
    job=jobs.claim(db,worker="timeout",capacity=1,queue=queue)
    started=time.monotonic()
    with pytest.raises(LeaseLost):_run_isolated(_blocked_process,job)
    assert time.monotonic()-started<10


def test_concurrent_promotion_creates_only_one_issue(db,world):
    from app.api.ai_intelligence import insight_to_issue
    from app.models.user import User
    from app.models.issue import Issue
    value=insight(world["project"].id);db.add(value);db.commit()
    project_id, insight_id, manager_id=world["project"].id,value.id,world["manager"].id
    start=Barrier(3);outcomes=[];errors=[]
    def promote():
        try:
            with SessionLocal() as session:
                person=session.get(User,manager_id)
                start.wait(timeout=5)
                try:outcomes.append(insight_to_issue(project_id,insight_id,session,person))
                except HTTPException as exc:
                    outcomes.append(exc.status_code);session.rollback()
        except Exception as exc:errors.append(exc)
    workers=[Thread(target=promote) for _ in range(2)]
    for t in workers:t.start()
    start.wait(timeout=5)
    for t in workers:t.join(timeout=15)
    assert not errors and all(not t.is_alive() for t in workers)
    assert sum(isinstance(o,dict) for o in outcomes)==1 and 409 in outcomes
    assert db.query(Issue).filter(Issue.project_id==project_id,Issue.category=="AI_INTELLIGENCE").count()==1


def test_conflicting_values_cannot_be_resolved_by_model_choice():
    from tests.test_phase2a_correctness import answer
    result=answer("Concrete grade C30 [1].","Concrete grade C30.\nConcrete grade C40.")
    assert not result.found and result.outcome=="CONFLICTING_EVIDENCE"


def test_durable_cooldown_defers_and_then_runs_trailing_event(db,world,queue,monkeypatch):
    from app.core.config import settings
    from app.services.domain_event_dispatcher import emit_domain_event
    from app.services.jobs.runner import run_pending
    from app.models.agent_run import AgentRun
    monkeypatch.setattr(settings,"AGENT_AUTO_ANALYSIS_ENABLED",True)
    def event():
        e=emit_domain_event(db,project_id=world["project"].id,event_type="TASK_UPDATED",
                            entity_type="TASK",entity_id=world["overdue"].id,
                            actor_user_id=world["manager"].id)
        db.commit();return e.id
    first=event();assert run_pending(queue=queue)==[("agents.handle_event","SUCCEEDED")]
    second=event();assert run_pending(queue=queue)==[("agents.handle_event","QUEUED")]
    assert db.query(AgentRun).filter(AgentRun.trigger_event_id==second).count()==0
    db.execute(text("UPDATE agent_runs SET created_at=now()-interval '11 minutes' WHERE project_id=:p"),{"p":world["project"].id})
    db.execute(text("UPDATE background_jobs SET run_after=now() WHERE queue=:q AND status='QUEUED'"),{"q":queue});db.commit()
    assert run_pending(queue=queue)==[("agents.handle_event","SUCCEEDED")]
    assert db.query(AgentRun).filter(AgentRun.trigger_event_id==second).count()==1


def test_failed_agent_and_notification_failure_roll_back_event_publication(db,world,queue,monkeypatch):
    from app.core.config import settings
    from app.services.domain_event_dispatcher import emit_domain_event
    from app.services.jobs.runner import run_pending
    from app.services.agents import event_subscriber
    from app.models.agent_run import AgentRun
    monkeypatch.setattr(settings,"AGENT_AUTO_ANALYSIS_ENABLED",True)
    event=emit_domain_event(db,project_id=world["project"].id,event_type="TASK_UPDATED",entity_type="TASK",
                            entity_id=world["overdue"].id,actor_user_id=world["manager"].id)
    event_id=event.id;db.commit()
    original=event_subscriber.notify_for_findings
    def crash(*args,**kwargs):raise RuntimeError("publication interrupted")
    monkeypatch.setattr(event_subscriber,"notify_for_findings",crash)
    assert run_pending(queue=queue)==[("agents.handle_event","QUEUED")]
    assert db.query(AgentRun).filter(AgentRun.trigger_event_id==event_id).count()==0
    monkeypatch.setattr(event_subscriber,"notify_for_findings",original)
    db.execute(text("UPDATE background_jobs SET run_after=now() WHERE queue=:q"),{"q":queue});db.commit()
    assert run_pending(queue=queue)==[("agents.handle_event","SUCCEEDED")]
    assert db.query(AgentRun).filter(AgentRun.trigger_event_id==event_id).count()==1


def test_source_access_revocation_hides_insight_tool_and_notification(db,world):
    from tests.office_roles import with_office_role
    from app.models.rbac import Discipline, UserDiscipline
    from app.models.notification import Notification
    from app.models.enums import NotificationType
    from app.api.notifications import get_notification
    from app.services.ai_tools.read_tools import get_findings
    from app.services.ai_tools.arguments import GetFindingsArguments
    user=world["site_engineer"]
    with_office_role(db,user,"senior_engineer")
    disciplines={d.code:d for d in db.query(Discipline).all()}
    assignment=UserDiscipline(user_id=user.id,discipline_id=disciplines["structural"].id)
    db.add(assignment)
    world["blocked"].discipline="structural"
    doc=Document(project_id=world["project"].id,uploaded_by_id=world["manager"].id,
                 task_id=world["blocked"].id,title="Structural specification",file_url="/unused")
    db.add(doc);db.flush()
    finding=AgentFinding(code="PRIVATE_REQUIREMENT",certainty=Certainty.DETECTED,severity="HIGH",confidence=.9,
                         title="Concrete requirement",description="Restricted source content",reason="Source",
                         recommended_action="Review",evidence=[Evidence("DOCUMENT",str(doc.id),doc.title)])
    value=_store(db,BY_NAME["document_consistency_agent"],world["project"].id,finding)
    db.flush()
    notification=Notification(user_id=user.id,title=value.title,message=value.description,type=NotificationType.SYSTEM,
                              project_id=world["project"].id,related_entity_type="AI_INSIGHT",related_entity_id=value.id)
    db.add(notification);db.commit()
    try:
        assert can_read_insight(db,user,value)
        assert get_notification(notification.id,db,user).id==notification.id
        assignment.discipline_id=disciplines["electrical"].id;db.commit()
        assert not can_read_insight(db,user,value)
        assert get_findings(db,user,world["project"].id,GetFindingsArguments())["findings"]==[]
        with pytest.raises(HTTPException) as exc:get_notification(notification.id,db,user)
        assert exc.value.status_code==404
    finally:
        db.delete(doc);db.commit()


def test_failed_agent_is_retried_instead_of_completing_job(db,world,queue,monkeypatch):
    from app.core.config import settings
    from app.services.domain_event_dispatcher import emit_domain_event
    from app.services.jobs.runner import run_pending
    monkeypatch.setattr(settings,"AGENT_AUTO_ANALYSIS_ENABLED",True)
    original=BY_NAME["schedule_risk_agent"]
    def broken(context):raise RuntimeError("fixture analyzer failure")
    monkeypatch.setitem(BY_NAME,"schedule_risk_agent",replace(original,analyzer=broken))
    emit_domain_event(db,project_id=world["project"].id,event_type="TASK_UPDATED",entity_type="TASK",
                      entity_id=world["overdue"].id,actor_user_id=world["manager"].id)
    db.commit()
    assert run_pending(queue=queue)==[("agents.handle_event","QUEUED")]
    monkeypatch.setitem(BY_NAME,"schedule_risk_agent",original)
    db.execute(text("UPDATE background_jobs SET run_after=now() WHERE queue=:q"),{"q":queue});db.commit()
    assert run_pending(queue=queue)==[("agents.handle_event","SUCCEEDED")]


def test_duplicate_and_out_of_order_events_keep_one_current_condition(db,world):
    from app.services.domain_event_dispatcher import emit_domain_event
    task=world["overdue"];task.status=TaskStatus.TODO
    task.progress_percentage=20;db.commit()
    def event(key):
        e=emit_domain_event(db,project_id=world["project"].id,event_type="TASK_UPDATED",entity_type="TASK",
                            entity_id=task.id,actor_user_id=world["manager"].id,idempotency_key=key)
        db.commit();return e.id
    first=event("same-input")
    assert event("same-input")==first
    second=event("new-input")
    values=db.query(AIInsight).filter(AIInsight.project_id==world["project"].id,
                                     AIInsight.insight_type=="PROGRESS_STATUS_CONFLICT").all()
    assert len(values)==1
    assert set(values[0].evidence_json["eventIds"])=={str(first),str(second)}


def test_document_listing_distinguishes_missing_from_unauthorized(db,world):
    from app.services.ai_tools import call_tool
    from app.models.user import User
    project_id=world["project"].id
    empty=call_tool(db,user=world["manager"],project_id=project_id,name="list_documents",arguments={})
    assert empty.ok and empty.data["sourceState"]=="NO_DOCUMENTS"
    doc=Document(project_id=project_id,uploaded_by_id=world["manager"].id,title="S102",file_url="/unused")
    db.add(doc);db.commit()
    try:
        owner=db.get(User,world["project"].owner_id)
        hidden=call_tool(db,user=owner,project_id=project_id,name="list_documents",arguments={})
        assert hidden.ok and hidden.data["sourceState"]=="NO_AUTHORIZED_DOCUMENTS"
        assert not hidden.data["documents"]
    finally:
        db.delete(doc);db.commit()


def test_engineering_documents_reach_real_retrieval_and_supported_excerpt_agent(db,world,monkeypatch):
    from app.services.rag.store import PgVectorStore, PreparedChunk, ChunkSource
    from app.services.rag.embeddings import EmbeddingService
    from app.services.rag.answering import AnswerService
    from app.services.ai_tools import read_tools
    from tests.answer_stub import ExtractiveAnswerClient
    from tests.embedding_stub import StubEmbeddingClient, STUB_MODEL
    monkeypatch.setattr(EmbeddingService,"_configured_client",lambda self:StubEmbeddingClient())
    monkeypatch.setattr(read_tools.rag,"AnswerService",lambda:AnswerService(client=ExtractiveAnswerClient()))
    docs=[]
    for title,content in [("S102 Structural specification","Concrete grade C30."),
                          ("Concrete workmanship specification","Concrete cover is 40 mm.")]:
        doc=Document(project_id=world["project"].id,uploaded_by_id=world["manager"].id,
                     title=title,document_type=DocumentType.SPECIFICATION,file_url="/unused",index_status="READY")
        db.add(doc);db.flush();docs.append(doc)
        vector=EmbeddingService().embed_one(content)
        PgVectorStore().add_chunks(db,source=ChunkSource.from_document(doc.id),project_id=world["project"].id,
                                   chunks=[PreparedChunk(1,0,content,6,vector)],embedding_model=STUB_MODEL,embedding_dim=len(vector))
    db.commit()
    try:
        result=run_agent(db,user=world["manager"],project_id=world["project"].id,
                         name="document_consistency_agent",persist=False)
        assert result.ok, result.as_json()
        requirements=next(f for f in result.findings if f.code=="DOCUMENT_REQUIREMENTS_RETRIEVED")
        assert requirements.certainty==Certainty.RECOMMENDATION
        assert requirements.confidence<=.7 and requirements.evidence
    finally:
        for doc in docs:db.delete(doc)
        db.commit()


def _publish_process(payload, attempt):
    from uuid import UUID
    with SessionLocal() as session:
        value=insight(UUID(payload["project_id"]))
        value.fingerprint=payload["fingerprint"]
        session.add(value);session.commit()


def test_spawned_worker_publishes_only_with_current_generation(db,world,queue,monkeypatch):
    from app.services.jobs.handlers import KINDS, JobKind
    from app.services.jobs.runner import execute
    fingerprint=uuid4().hex
    monkeypatch.setitem(KINDS,"test.process",JobKind("test.process",_publish_process,True))
    jobs.enqueue(db,"test.process",{"project_id":world["project"].id,"fingerprint":fingerprint},queue=queue)
    db.commit()
    job=jobs.claim(db,worker="spawned",capacity=1,queue=queue)
    assert execute(job,isolated=True)=="SUCCEEDED"
    assert db.query(AIInsight).filter(AIInsight.fingerprint==fingerprint).count()==1


def test_forced_source_reclaim_fences_old_failure_and_publication(db,world):
    from app.services.rag.ingestion import (_Target, _claim, _fail, _assert_source_owned,
                                           IndexingSuperseded)
    from dataclasses import replace
    doc=Document(project_id=world["project"].id,uploaded_by_id=world["manager"].id,
                 title="Concurrent indexing",file_url="/unused")
    db.add(doc);db.commit()
    try:
        target=_Target.for_document(doc)
        old=replace(target,claimed_at=_claim(db,target,force=False))
        fresh=replace(target,claimed_at=_claim(db,target,force=True))
        with pytest.raises(IndexingSuperseded):_assert_source_owned(db,old)
        db.rollback()
        with pytest.raises(IndexingSuperseded):_fail(db,old,"old failure")
        db.rollback()
        _assert_source_owned(db,fresh)
        db.expire_all()
        assert db.get(Document,doc.id).index_status=="INDEXING"
        db.rollback()
    finally:
        db.delete(doc);db.commit()


def test_run_record_failure_is_retried_atomically(db,world,queue,monkeypatch):
    from sqlalchemy import event as sql_event
    from sqlalchemy.orm import Session
    from app.models.agent_run import AgentRun
    from app.core.config import settings
    from app.services.domain_event_dispatcher import emit_domain_event
    from app.services.jobs.runner import run_pending
    monkeypatch.setattr(settings,"AGENT_AUTO_ANALYSIS_ENABLED",True)
    e=emit_domain_event(db,project_id=world["project"].id,event_type="TASK_UPDATED",entity_type="TASK",
                        entity_id=world["overdue"].id,actor_user_id=world["manager"].id)
    event_id=e.id;db.commit()
    def reject_record(session,*args):
        if session.info.get("agent_event_transaction") and any(isinstance(i,AgentRun) for i in session.new):
            raise RuntimeError("run record publication failed")
    sql_event.listen(Session,"before_flush",reject_record)
    try:
        assert run_pending(queue=queue)==[("agents.handle_event","QUEUED")]
    finally:
        sql_event.remove(Session,"before_flush",reject_record)
    assert db.query(AgentRun).filter(AgentRun.trigger_event_id==event_id).count()==0
    db.execute(text("UPDATE background_jobs SET run_after=now() WHERE queue=:q"),{"q":queue});db.commit()
    assert run_pending(queue=queue)==[("agents.handle_event","SUCCEEDED")]


def test_promotion_does_not_copy_restricted_technical_text_into_public_work(db,world):
    from app.api.ai_intelligence import insight_to_issue
    from app.models.issue import Issue
    doc=Document(project_id=world["project"].id,uploaded_by_id=world["manager"].id,
                 title="Restricted grade C90 specification",file_url="/unused")
    db.add(doc);db.flush()
    f=AgentFinding(code="PRIVATE_CONTENT",certainty=Certainty.DETECTED,severity="HIGH",confidence=.9,
                   title="Restricted grade C90",description="Restricted numerical requirement C90",
                   reason="Source",recommended_action="Review",
                   evidence=[Evidence("DOCUMENT",str(doc.id),doc.title)])
    value=_store(db,BY_NAME["document_consistency_agent"],world["project"].id,f);db.commit()
    try:
        result=insight_to_issue(world["project"].id,value.id,db,world["manager"])
        work=db.get(Issue,result["id"])
        assert "C90" not in work.title+work.description and str(value.id) in work.description
    finally:
        db.delete(doc);db.commit()


def test_ai_push_intent_is_durable_and_rollback_safe(db,world,queue,monkeypatch):
    from app.core.config import settings
    from app.services.push.dispatcher import queue_push
    from app.services.push.base import PushMessage
    from app.models.background_job import BackgroundJob
    monkeypatch.setattr(settings,"PUSH_ENABLED",True)
    notification_id=uuid4()
    message=PushMessage("Review","Restricted evidence",notification_id=notification_id,
                         data={"entityType":"AI_INSIGHT","entityId":str(uuid4())})
    queue_push(db,user_id=world["manager"].id,message=message)
    db.rollback()
    assert db.query(BackgroundJob).filter(BackgroundJob.queue==queue).count()==0
    queue_push(db,user_id=world["manager"].id,message=message);db.commit()
    row=db.query(BackgroundJob).filter(BackgroundJob.queue==queue).one()
    assert row.kind=="push.deliver_notification" and row.status=="QUEUED"
    assert "Restricted" not in str(row.payload)

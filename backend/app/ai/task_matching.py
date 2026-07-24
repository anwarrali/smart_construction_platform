import re
from difflib import SequenceMatcher
from uuid import UUID

from app.ai.action_schemas import TaskCandidate, VoiceAction


def task_candidate(task) -> TaskCandidate:
    return TaskCandidate(
        id=task.id,
        task_code=task.task_code,
        name=task.name,
        status=task.status.value,
        progress_percentage=float(task.progress_percentage or 0),
        discipline=task.discipline,
    )


def resolve_task(action: VoiceAction, tasks: list) -> tuple[VoiceAction, TaskCandidate | None, list[TaskCandidate]]:
    by_id = {task.id: task for task in tasks}
    if action.task_id in by_id:
        selected = task_candidate(by_id[action.task_id])
        return action.model_copy(update={"task_reference": selected.name}), selected, []

    reference = _normalize(action.task_reference or "")
    if not reference:
        return action.model_copy(update={"task_id": None, "requires_clarification": True}), None, [
            task_candidate(task) for task in tasks[:5]
        ]

    scored: list[tuple[float, object]] = []
    for task in tasks:
        names = (_normalize(task.name), _normalize(task.task_code))
        score = max(_similarity(reference, value) for value in names if value)
        scored.append((score, task))
    scored.sort(key=lambda item: item[0], reverse=True)
    plausible = [(score, task) for score, task in scored if score >= 0.58][:5]
    if not plausible:
        return action.model_copy(update={"task_id": None, "requires_clarification": True}), None, [
            task_candidate(task) for _, task in scored[:5]
        ]
    top_score, top_task = plausible[0]
    ambiguous = len(plausible) > 1 and top_score - plausible[1][0] < 0.12
    if top_score < 0.72 or ambiguous:
        return action.model_copy(update={"task_id": None, "requires_clarification": True}), None, [
            task_candidate(task) for _, task in plausible
        ]
    selected = task_candidate(top_task)
    return action.model_copy(update={
        "task_id": selected.id,
        "task_reference": selected.name,
        "requires_clarification": False,
    }), selected, []


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"\w+", value.casefold(), flags=re.UNICODE))


def _similarity(left: str, right: str) -> float:
    if left == right:
        return 1.0
    if left in right or right in left:
        return min(len(left), len(right)) / max(len(left), len(right)) * 0.25 + 0.72
    return SequenceMatcher(None, left, right).ratio()

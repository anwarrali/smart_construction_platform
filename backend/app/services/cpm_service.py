"""Dependency-driven Critical Path Method calculations.

The primary path returned by this module is always a connected, ordered chain of
task dependency edges.  Isolated tasks are deliberately excluded: an isolated
long task is not a dependency path and must never be presented as one.
"""
from __future__ import annotations

from collections import deque
from typing import Any, Sequence

from app.core.schedule_dates import inclusive_duration_days


def _duration(task: Any) -> int:
    start_date = getattr(task, "planned_start_date", None)
    end_date = getattr(task, "planned_end_date", None)
    if start_date is not None and end_date is not None:
        return inclusive_duration_days(start_date, end_date)
    return max(1, int(task.duration_days or 1))


def _dependency_type(dependency: Any) -> str:
    value = dependency.dependency_type
    return value.value if hasattr(value, "value") else str(value).lower()


def _start_offset(dependency: Any, predecessor: Any, successor: Any) -> int:
    """Convert a precedence relationship into a successor-start constraint."""
    lag = int(dependency.lag_days or 0)
    relation = _dependency_type(dependency)
    predecessor_duration = _duration(predecessor)
    successor_duration = _duration(successor)
    if relation == "start_to_start":
        return lag
    if relation == "finish_to_finish":
        return predecessor_duration + lag - successor_duration
    if relation == "start_to_finish":
        return lag - successor_duration
    # FINISH_TO_START is the construction scheduling default.
    return predecessor_duration + lag


def calculate_dependency_cpm(tasks: Sequence[Any], dependencies: Sequence[Any]) -> dict[str, Any]:
    """Run CPM and reconstruct one deterministic, connected primary path.

    Multiple zero-float branches may exist.  ``critical_task_ids`` represents a
    single primary driving path, selected deterministically when branches tie.
    """
    by_id = {task.id: task for task in tasks}
    valid_dependencies = [
        dependency for dependency in dependencies
        if dependency.task_id in by_id and dependency.depends_on_task_id in by_id
    ]
    predecessors: dict[Any, list[tuple[Any, Any]]] = {task_id: [] for task_id in by_id}
    successors: dict[Any, list[tuple[Any, Any]]] = {task_id: [] for task_id in by_id}
    participants: set[Any] = set()
    for dependency in valid_dependencies:
        predecessors[dependency.task_id].append((dependency.depends_on_task_id, dependency))
        successors[dependency.depends_on_task_id].append((dependency.task_id, dependency))
        participants.update((dependency.task_id, dependency.depends_on_task_id))

    def sort_key(task_id: Any) -> tuple[int, str, str]:
        task = by_id[task_id]
        return (int(getattr(task, "sort_order", 0) or 0), str(task.name).lower(), str(task_id))

    indegree = {task_id: len(items) for task_id, items in predecessors.items()}
    ready = deque(sorted((task_id for task_id, degree in indegree.items() if degree == 0), key=sort_key))
    order: list[Any] = []
    while ready:
        task_id = ready.popleft()
        order.append(task_id)
        for successor_id, _dependency in sorted(successors[task_id], key=lambda item: sort_key(item[0])):
            indegree[successor_id] -= 1
            if indegree[successor_id] == 0:
                ready.append(successor_id)
        ready = deque(sorted(ready, key=sort_key))
    if len(order) != len(tasks):
        raise ValueError("Task dependency graph contains a cycle")

    if not valid_dependencies:
        return {
            "project_duration_days": 0,
            "critical_task_ids": [],
            "details": [],
            "dependency_count": 0,
            "reason": "No task dependencies exist. CPM requires a connected dependency chain.",
        }

    earliest_start: dict[Any, int] = {}
    earliest_finish: dict[Any, int] = {}
    for task_id in order:
        constraints = [
            earliest_start[pred_id] + _start_offset(dependency, by_id[pred_id], by_id[task_id])
            for pred_id, dependency in predecessors[task_id]
        ]
        earliest_start[task_id] = max(0, max(constraints, default=0))
        earliest_finish[task_id] = earliest_start[task_id] + _duration(by_id[task_id])

    project_duration = max((earliest_finish[task_id] for task_id in participants), default=0)
    latest_start = {
        task_id: project_duration - _duration(by_id[task_id])
        for task_id in participants
    }
    for task_id in reversed(order):
        if task_id not in participants:
            continue
        successor_limits = [
            latest_start[successor_id] - _start_offset(dependency, by_id[task_id], by_id[successor_id])
            for successor_id, dependency in successors[task_id]
        ]
        if successor_limits:
            latest_start[task_id] = min(latest_start[task_id], min(successor_limits))

    total_float = {
        task_id: latest_start[task_id] - earliest_start[task_id]
        for task_id in participants
    }

    # Start at a zero-float activity that drives project completion, then follow
    # only tight (driving) predecessor constraints.  This guarantees adjacency.
    finish_candidates = [
        task_id for task_id in participants
        if earliest_finish[task_id] == project_duration and total_float[task_id] == 0
    ]
    current = sorted(finish_candidates, key=sort_key)[0] if finish_candidates else None
    reverse_path: list[Any] = []
    driving_edges: dict[Any, Any] = {}
    while current is not None:
        reverse_path.append(current)
        candidates = []
        for predecessor_id, dependency in predecessors[current]:
            constraint = earliest_start[predecessor_id] + _start_offset(
                dependency, by_id[predecessor_id], by_id[current]
            )
            if constraint == earliest_start[current] and total_float.get(predecessor_id) == 0:
                candidates.append((predecessor_id, dependency))
        if not candidates:
            break
        predecessor_id, dependency = sorted(candidates, key=lambda item: sort_key(item[0]))[0]
        driving_edges[current] = dependency
        current = predecessor_id

    critical_path = list(reversed(reverse_path))
    # A lone activity is not a dependency path.  This prevents the exact
    # longest-task fallback that CPM users find misleading.
    if len(critical_path) < 2:
        critical_path = []
        reason = "Dependencies exist, but no connected dependency chain drives the project finish."
    else:
        reason = None
    critical_ids = set(critical_path)

    details = []
    for task_id in order:
        if task_id not in participants:
            continue
        dependency = driving_edges.get(task_id)
        predecessor_id = dependency.depends_on_task_id if dependency is not None else None
        details.append({
            "task_id": task_id,
            "name": by_id[task_id].name,
            "duration_days": _duration(by_id[task_id]),
            "earliest_start": earliest_start[task_id],
            "earliest_finish": earliest_finish[task_id],
            "latest_start": latest_start[task_id],
            "latest_finish": latest_start[task_id] + _duration(by_id[task_id]),
            "total_float_days": total_float[task_id],
            "is_critical": task_id in critical_ids,
            "predecessor_ids": [pred_id for pred_id, _ in predecessors[task_id]],
            "driving_predecessor_id": predecessor_id,
            "driving_dependency_type": _dependency_type(dependency) if dependency is not None else None,
            "driving_lag_days": int(dependency.lag_days or 0) if dependency is not None else 0,
        })

    return {
        "project_duration_days": project_duration,
        "critical_task_ids": critical_path,
        "details": details,
        "dependency_count": len(valid_dependencies),
        "reason": reason,
    }

from types import SimpleNamespace
from unittest import TestCase
from datetime import date

from app.services.cpm_service import calculate_dependency_cpm


def task(task_id: str, duration: int, name: str | None = None):
    return SimpleNamespace(id=task_id, name=name or task_id, duration_days=duration, sort_order=0)


def dependency(predecessor_id: str, successor_id: str, lag: int = 0):
    return SimpleNamespace(
        task_id=successor_id,
        depends_on_task_id=predecessor_id,
        dependency_type="finish_to_start",
        lag_days=lag,
    )


def dated_task(task_id: str, start: date, end: date):
    return SimpleNamespace(
        id=task_id,
        name=task_id,
        planned_start_date=start,
        planned_end_date=end,
        duration_days=999,
        sort_order=0,
    )


class DependencyCpmTests(TestCase):
    def test_isolated_longest_task_is_not_the_critical_path(self):
        tasks = [task("isolated", 100), task("foundation", 5), task("frame", 7)]
        result = calculate_dependency_cpm(tasks, [dependency("foundation", "frame")])

        self.assertEqual(result["critical_task_ids"], ["foundation", "frame"])
        self.assertEqual(result["project_duration_days"], 12)
        self.assertNotIn("isolated", result["critical_task_ids"])

    def test_reconstructs_the_driving_branch_in_dependency_order(self):
        tasks = [task("start", 3), task("short", 4), task("long", 6), task("finish", 2)]
        dependencies = [
            dependency("start", "short"),
            dependency("start", "long"),
            dependency("short", "finish"),
            dependency("long", "finish"),
        ]
        result = calculate_dependency_cpm(tasks, dependencies)

        self.assertEqual(result["critical_task_ids"], ["start", "long", "finish"])
        self.assertEqual(result["project_duration_days"], 11)
        critical_details = [item for item in result["details"] if item["is_critical"]]
        self.assertTrue(all(item["total_float_days"] == 0 for item in critical_details))

    def test_lag_is_included_in_forward_and_backward_passes(self):
        tasks = [task("a", 2), task("b", 3)]
        result = calculate_dependency_cpm(tasks, [dependency("a", "b", lag=4)])

        self.assertEqual(result["project_duration_days"], 9)
        self.assertEqual(result["critical_task_ids"], ["a", "b"])

    def test_no_dependencies_returns_no_path_instead_of_longest_task(self):
        result = calculate_dependency_cpm([task("long", 100), task("short", 1)], [])

        self.assertEqual(result["critical_task_ids"], [])
        self.assertEqual(result["project_duration_days"], 0)
        self.assertIn("requires a connected dependency chain", result["reason"])

    def test_cycle_is_rejected(self):
        tasks = [task("a", 2), task("b", 3)]
        with self.assertRaisesRegex(ValueError, "cycle"):
            calculate_dependency_cpm(tasks, [dependency("a", "b"), dependency("b", "a")])

    def test_cpm_uses_inclusive_date_durations_without_changing_chain_order(self):
        tasks = [
            dated_task("a", date(2026, 7, 14), date(2026, 7, 16)),
            dated_task("b", date(2026, 7, 17), date(2026, 7, 20)),
            dated_task("c", date(2026, 7, 21), date(2026, 7, 21)),
        ]
        result = calculate_dependency_cpm(
            tasks,
            [dependency("a", "b"), dependency("b", "c")],
        )

        self.assertEqual(result["critical_task_ids"], ["a", "b", "c"])
        self.assertEqual(result["project_duration_days"], 8)
        self.assertEqual([item["duration_days"] for item in result["details"]], [3, 4, 1])

"""What the engineer said, against what the project actually contains.

These tests encode the product rule that matters more than accuracy: the
matcher may be wrong, but it may never be *confidently* wrong. Every case that
is genuinely ambiguous must come back ambiguous, because the alternative is a
task marked complete that nobody completed.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from uuid import uuid4

from app.services.voice_task_matcher import (
    AMBIGUITY_MARGIN,
    MAX_CANDIDATES,
    concepts,
    match_task,
    normalize,
    rank_tasks,
)


def task(code, name, *, discipline=None, status="todo", progress=0.0, description=None):
    return SimpleNamespace(
        id=uuid4(),
        task_code=code,
        name=name,
        discipline=discipline,
        status=status,
        progress_percentage=progress,
        description=description,
    )


def project_tasks():
    """A deliberately confusable project: three tasks differ by one word."""
    return [
        task("EL-101", "First Floor - Electrical Installation",
             discipline="electrical", status="in_progress", progress=60),
        task("EL-102", "First Floor - Electrical Fixtures", discipline="electrical"),
        task("EL-103", "First Floor - Electrical Inspection", discipline="electrical"),
        task("EL-201", "Second Floor - Electrical Installation", discipline="electrical"),
        task("CN-010", "Concrete Preparation - Foundation",
             discipline="civil", status="in_progress", progress=40),
        task("PL-050", "Building B - Plastering Works", discipline="civil"),
        task("CE-070", "Second Floor - Ceiling Installation", discipline="civil"),
    ]


def codes(matches):
    return [match.task_code for match in matches]


class NormalizationTests(TestCase):
    def test_arabic_orthographic_variants_fold_together(self):
        # The same dictated word, spelled four ways by four transcriptions.
        forms = ["الأول", "الاول", "الأوّل", "الآول"]
        self.assertEqual(len({normalize(form) for form in forms}), 1)

    def test_arabic_indic_digits_become_ascii(self):
        self.assertEqual(normalize("الطابق ١"), normalize("الطابق 1"))

    def test_concepts_cross_the_language_boundary(self):
        self.assertIn("plaster", concepts("خلصنا القصارة"))
        self.assertIn("plaster", concepts("plastering finished"))
        self.assertIn("electrical", concepts("تمديدات كهربائية"))
        self.assertIn("concrete", concepts("صب الباطون"))


class ClearUpdateTests(TestCase):
    """Case A — a statement with one plausible task must resolve to it."""

    def test_unique_work_resolves_without_a_question(self):
        tasks = project_tasks()
        outcome = match_task("Concrete preparation is done", tasks)
        self.assertTrue(outcome.is_resolved)
        self.assertEqual(
            outcome.resolved_task_id,
            next(item.id for item in tasks if item.task_code == "CN-010"),
        )

    def test_location_separates_otherwise_identical_tasks(self):
        outcome = match_task(
            "we finished the ceiling installation on the second floor", project_tasks()
        )
        self.assertTrue(outcome.is_resolved)
        self.assertEqual(outcome.candidates[0].task_code, "CE-070")

    def test_spoken_task_code_outranks_everything_else(self):
        outcome = match_task("update EL-201 please", project_tasks())
        self.assertTrue(outcome.is_resolved)
        self.assertEqual(outcome.candidates[0].task_code, "EL-201")

    def test_the_best_candidate_is_still_ranked_first_when_ambiguous(self):
        # Case A as the spec words it: "electrical work on first floor is
        # complete" cannot resolve against three first-floor electrical tasks,
        # but the installation task must still lead the list.
        matches = rank_tasks("Electrical work on first floor is complete", project_tasks())
        self.assertEqual(matches[0].task_code, "EL-101")


class AmbiguityTests(TestCase):
    """Case B — similar candidates must produce a question, never a guess."""

    def test_bare_discipline_does_not_resolve(self):
        outcome = match_task("electrical work is finished", project_tasks())
        self.assertFalse(outcome.is_resolved)
        self.assertTrue(outcome.is_ambiguous)
        self.assertIn("EL-101", codes(outcome.candidates))

    def test_candidate_list_stays_short_enough_to_read(self):
        outcome = match_task("electrical work is finished", project_tasks())
        self.assertLessEqual(len(outcome.candidates), MAX_CANDIDATES)
        self.assertGreaterEqual(len(outcome.candidates), 2)

    def test_near_ties_are_never_resolved_however_high_they_score(self):
        outcome = match_task("خلصنا first floor electrical work", project_tasks())
        self.assertFalse(outcome.is_resolved)
        top, second = outcome.candidates[0].score, outcome.candidates[1].score
        self.assertLess(top - second, AMBIGUITY_MARGIN)

    def test_a_contradicted_location_is_ranked_below_a_matching_one(self):
        matches = rank_tasks("first floor electrical installation", project_tasks())
        self.assertLess(
            next(match.score for match in matches if match.task_code == "EL-201"),
            next(match.score for match in matches if match.task_code == "EL-101"),
        )


class MultipleUpdateTests(TestCase):
    """Case C — a daily update names several tasks; each resolves separately."""

    def test_each_spoken_activity_resolves_to_its_own_task(self):
        tasks = project_tasks()
        first = match_task("concrete preparation finished", tasks)
        second = match_task("started plastering in building B", tasks)
        self.assertTrue(first.is_resolved)
        self.assertTrue(second.is_resolved)
        self.assertEqual(first.candidates[0].task_code, "CN-010")
        self.assertEqual(second.candidates[0].task_code, "PL-050")
        self.assertNotEqual(first.resolved_task_id, second.resolved_task_id)


class ArabicTests(TestCase):
    """Cases D and E — Arabic and mixed speech against English task names."""

    def test_arabic_speech_matches_english_task_names(self):
        matches = rank_tasks("خلصنا شغل الكهرباء بالطابق الأول", project_tasks())
        self.assertEqual(matches[0].task_code, "EL-101")
        self.assertIn("level:1", matches[0].reasons)

    def test_arabic_floor_beats_the_wrong_floor(self):
        matches = rank_tasks("خلصنا شغل الكهرباء بالطابق الأول", project_tasks())
        self.assertNotIn("EL-201", codes(matches[:3]))

    def test_arabic_plastering_reaches_the_plastering_task(self):
        outcome = match_task("بلشنا القصارة في مبنى B", project_tasks())
        self.assertEqual(outcome.candidates[0].task_code, "PL-050")

    def test_mixed_language_is_understood_as_one_sentence(self):
        matches = rank_tasks("خلصنا first floor electrical work", project_tasks())
        self.assertTrue(all(code.startswith("EL-1") for code in codes(matches[:3])))


class UnknownAndLowConfidenceTests(TestCase):
    """Cases F and G — nothing recognizable must never become an action."""

    def test_a_vague_reference_resolves_to_nothing(self):
        outcome = match_task("خلصنا الشغل اللي حكيتلك عنه", project_tasks())
        self.assertFalse(outcome.is_resolved)
        self.assertLess(outcome.confidence, 0.3)

    def test_a_vague_reference_still_offers_a_way_forward(self):
        outcome = match_task("خلصنا الشغل اللي حكيتلك عنه", project_tasks())
        self.assertTrue(outcome.candidates)
        self.assertLessEqual(len(outcome.candidates), MAX_CANDIDATES)

    def test_silence_offers_candidates_but_chooses_none(self):
        outcome = match_task("", project_tasks())
        self.assertFalse(outcome.is_resolved)
        self.assertEqual(outcome.confidence, 0.0)

    def test_an_empty_project_produces_no_candidates_and_no_crash(self):
        outcome = match_task("electrical work finished", [])
        self.assertFalse(outcome.is_resolved)
        self.assertEqual(outcome.candidates, [])


class RankingPriorTests(TestCase):
    def test_completed_work_is_the_least_likely_subject_of_an_update(self):
        tasks = [
            task("EL-101", "First Floor - Electrical Installation",
                 discipline="electrical", status="done", progress=100),
            task("EL-104", "First Floor - Electrical Installation Rework",
                 discipline="electrical", status="in_progress", progress=20),
        ]
        matches = rank_tasks("first floor electrical installation", tasks)
        self.assertEqual(matches[0].task_code, "EL-104")

    def test_the_status_prior_cannot_by_itself_break_a_tie_into_a_decision(self):
        # Two identically named tasks differing only in status must stay
        # ambiguous: a prior orders candidates, it never chooses between them.
        tasks = [
            task("A-1", "Electrical Installation", status="in_progress"),
            task("A-2", "Electrical Installation", status="TODO"),
        ]
        self.assertFalse(match_task("electrical installation", tasks).is_resolved)


class CandidateContractTests(TestCase):
    def test_an_option_carries_what_the_engineer_needs_to_choose(self):
        outcome = match_task("electrical work is finished", project_tasks())
        option = outcome.candidates[0].as_option()
        self.assertEqual(set(option) >= {"value", "label", "status", "reasons"}, True)
        self.assertIn("—", option["label"])

    def test_reasons_explain_the_match_in_the_engineers_terms(self):
        matches = rank_tasks("first floor electrical work", project_tasks())
        self.assertIn("electrical", matches[0].reasons)
        self.assertIn("level:1", matches[0].reasons)


class CandidateEndpointScopeTests(TestCase):
    """Case H at the retrieval boundary: the query cannot widen the task set."""

    def test_candidates_are_ranked_only_from_the_authorized_task_list(self):
        from app.api.voice import voice_task_candidates

        mine = project_tasks()
        project_id = uuid4()
        user = SimpleNamespace(id=uuid4())

        with patch("app.api.voice.authorized_voice_tasks", return_value=mine) as authorized:
            response = voice_task_candidates(
                project_id=project_id, q="electrical work finished", limit=5,
                db=SimpleNamespace(), current_user=user,
            )

        authorized.assert_called_once_with(authorized.call_args[0][0], user, project_id)
        returned = {candidate.task_id for candidate in response.candidates}
        self.assertTrue(returned <= {item.id for item in mine})

    def test_no_accessible_task_yields_no_candidates(self):
        from app.api.voice import voice_task_candidates

        with patch("app.api.voice.authorized_voice_tasks", return_value=[]):
            response = voice_task_candidates(
                project_id=uuid4(), q="electrical", limit=5,
                db=SimpleNamespace(), current_user=SimpleNamespace(id=uuid4()),
            )
        self.assertEqual(response.candidates, [])
        self.assertIsNone(response.resolved_task_id)


class MatchingCostTests(TestCase):
    """A guard on the shape of the cost, not on the wall clock.

    Timing assertions are flaky on shared CI, so this measures the thing that
    actually regressed: how many times the quadratic string comparison runs.
    Before head refinement it ran once per task, which made a large project's
    ranking cost a visible fraction of a second on every spoken action.
    """

    def _large_project(self, count=400):
        return [
            task(
                f"T-{index:04d}",
                f"{'First' if index % 3 else 'Second'} Floor - Package {index}",
                discipline="electrical" if index % 4 == 0 else "civil",
            )
            for index in range(count)
        ]

    def test_similarity_runs_on_the_head_of_the_list_only(self):
        from app.services import voice_task_matcher

        tasks = self._large_project()
        with patch.object(
            voice_task_matcher, "_fuzzy", wraps=voice_task_matcher._fuzzy
        ) as fuzzy:
            voice_task_matcher.match_task("first floor electrical work", tasks)

        self.assertLessEqual(fuzzy.call_count, voice_task_matcher.REFINE_WIDTH)
        self.assertLess(fuzzy.call_count, len(tasks))

    def test_a_small_project_is_scored_once_not_twice(self):
        from app.services import voice_task_matcher

        tasks = project_tasks()
        with patch.object(
            voice_task_matcher, "score_task", wraps=voice_task_matcher.score_task
        ) as scorer:
            voice_task_matcher.match_task("concrete preparation done", tasks)

        self.assertEqual(scorer.call_count, len(tasks))

    def test_task_features_are_parsed_once_per_distinct_text(self):
        from app.services import voice_task_matcher

        tasks = project_tasks()
        voice_task_matcher._features.cache_clear()
        for _ in range(5):
            voice_task_matcher.match_task("electrical work finished", tasks)
        info = voice_task_matcher._features.cache_info()
        self.assertGreater(info.hits, info.misses)

    def test_refinement_does_not_change_which_task_wins(self):
        # The optimization must be invisible in the result, not merely fast.
        from app.services import voice_task_matcher

        tasks = self._large_project() + project_tasks()
        spoken = "concrete preparation is done"
        reference = voice_task_matcher.SpokenReference.parse(spoken)
        exhaustive = sorted(
            (voice_task_matcher.score_task(reference, item) for item in tasks),
            key=lambda match: match.score,
            reverse=True,
        )
        self.assertEqual(
            match_task(spoken, tasks).candidates[0].task_code,
            exhaustive[0].task_code,
        )

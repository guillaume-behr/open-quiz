"""The scoring rule and question maximums, exercised without FastAPI."""

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import hash_password
from app.models import Question, QuestionBank, QuestionChoice, User
from app.services import grading
from app.services.grading import (
    compute_final_scores,
    decoded_answer_data,
    question_maximum_scores,
    selected_choice_ids,
    selected_choice_score,
)

from support import (
    session_factory_for,
    settings_for,
)


def test_selecting_wrong_choices_cancels_non_negative_partial_credit() -> None:
    choices = [
        QuestionChoice(id=1, is_correct=True, points=1.5),
        QuestionChoice(id=2, is_correct=True, points=0.5),
        QuestionChoice(id=3, is_correct=False, points=-1),
    ]

    assert (
        selected_choice_score(
            choices,
            {1},
            allow_negative_points=False,
        )
        == 1.5
    )
    assert (
        selected_choice_score(
            choices,
            {1, 2, 3},
            allow_negative_points=False,
        )
        == 0
    )
    assert (
        selected_choice_score(
            choices,
            {1, 2, 3},
            allow_negative_points=True,
        )
        == 1
    )


def test_negative_points_do_not_make_selecting_every_choice_free() -> None:
    """Ticking every box must never pay, whatever the quiz allows.

    The question editor defaults a distractor to zero points, so enabling
    negative points on the quiz used to drop the wrong-answer penalty without
    putting one in its place: selecting everything collected the whole key and
    scored full marks without reading the question.
    """
    choices = [
        QuestionChoice(id=1, is_correct=True, points=1),
        QuestionChoice(id=2, is_correct=False, points=0),
        QuestionChoice(id=3, is_correct=False, points=0),
    ]
    every_choice = {1, 2, 3}

    for allow_negative_points in (False, True):
        assert (
            selected_choice_score(
                choices,
                {1},
                allow_negative_points=allow_negative_points,
            )
            == 1
        )
        assert (
            selected_choice_score(
                choices,
                every_choice,
                allow_negative_points=allow_negative_points,
            )
            == 0
        ), (
            f"selecting every choice paid with allow_negative_points={allow_negative_points}"
        )

    # A distractor the teacher did price is still charged as written rather
    # than cancelling the whole question.
    priced = [
        QuestionChoice(id=1, is_correct=True, points=1),
        QuestionChoice(id=2, is_correct=False, points=-0.5),
    ]
    assert selected_choice_score(priced, {1, 2}, allow_negative_points=True) == 0.5
    assert selected_choice_score(priced, {1, 2}, allow_negative_points=False) == 0


def test_no_questions_have_no_maximums() -> None:
    assert question_maximum_scores([], session=None) == {}


class _Answers:
    def __init__(self, answers: list[Any]) -> None:
        self.answers = answers

    def scalars(self, _statement: object) -> list[Any]:
        return self.answers


def test_training_results_skip_missing_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written = SimpleNamespace(id=1, answer_mode="written")
    choice = SimpleNamespace(id=2, answer_mode="single")
    answers = [SimpleNamespace(question_id=2, answer_data="{}")]
    monkeypatch.setattr(
        grading,
        "load_question_records",
        lambda *_: ({1: written, 2: choice}, {1: [], 2: []}),
    )
    monkeypatch.setattr(grading, "question_maximum_scores", lambda *_: {2: 1.0})
    quiz_session = SimpleNamespace(id=1)
    participant = SimpleNamespace(id=1)

    monkeypatch.setattr(grading, "session_question_ids", lambda *_: [3, 1, 2])
    assert grading.training_result(quiz_session, participant, _Answers(answers)) == (
        0.0,
        1.0,
        0,
    )
    monkeypatch.setattr(grading, "session_question_ids", lambda *_: [])
    assert grading.training_result(quiz_session, participant, _Answers([])) == (
        0.0,
        0.0,
        0,
    )


def choice(choice_id: int, *, correct: bool, points: float) -> QuestionChoice:
    return QuestionChoice(id=choice_id, is_correct=correct, points=points)


@pytest.mark.parametrize("allow_negative_points", [False, True])
def test_an_empty_selection_scores_zero(allow_negative_points: bool) -> None:
    choices = [choice(1, correct=True, points=1), choice(2, correct=False, points=-1)]
    assert (
        selected_choice_score(
            choices, set(), allow_negative_points=allow_negative_points
        )
        == 0
    )


def test_a_question_without_choices_scores_zero() -> None:
    assert selected_choice_score([], {1, 2}, allow_negative_points=True) == 0


def test_selected_ids_from_another_question_are_ignored() -> None:
    # A forged payload can name any id: only this question's choices count.
    choices = [choice(1, correct=True, points=2)]
    assert selected_choice_score(choices, {1, 999}, allow_negative_points=False) == 2


def test_scores_are_rounded_to_two_decimals() -> None:
    choices = [
        choice(1, correct=True, points=0.1),
        choice(2, correct=True, points=0.2),
        choice(3, correct=True, points=1 / 3),
    ]
    assert selected_choice_score(choices, {1, 2}, allow_negative_points=False) == 0.3
    assert (
        selected_choice_score(choices, {1, 2, 3}, allow_negative_points=False) == 0.63
    )


def test_a_negative_correct_choice_only_costs_in_negative_mode() -> None:
    choices = [
        choice(1, correct=True, points=2),
        choice(2, correct=True, points=-0.5),
    ]
    assert selected_choice_score(choices, {1, 2}, allow_negative_points=False) == 2
    assert selected_choice_score(choices, {1, 2}, allow_negative_points=True) == 1.5


def test_a_priced_distractor_alone_scores_below_zero_in_negative_mode() -> None:
    choices = [
        choice(1, correct=True, points=1),
        choice(2, correct=False, points=-0.5),
    ]
    assert selected_choice_score(choices, {2}, allow_negative_points=True) == -0.5
    assert selected_choice_score(choices, {2}, allow_negative_points=False) == 0


def test_a_positive_distractor_still_zeroes_the_question_in_negative_mode() -> None:
    choices = [
        choice(1, correct=True, points=1),
        choice(2, correct=False, points=0.5),
        choice(3, correct=False, points=-0.25),
    ]
    assert selected_choice_score(choices, {1, 2, 3}, allow_negative_points=True) == 0


def stored_answer(answer_data: str) -> SimpleNamespace:
    return SimpleNamespace(answer_data=answer_data)


@pytest.mark.parametrize(
    ("answer_data", "expected"),
    [
        ("{}", set()),
        ('{"selected_choice_ids": null}', set()),
        ('{"selected_choice_ids": "12"}', set()),
        ('{"selected_choice_ids": 12}', set()),
        ('{"selected_choice_ids": {"1": true}}', set()),
        ('{"selected_choice_ids": []}', set()),
        ('{"selected_choice_ids": [1, 1, 2]}', {1, 2}),
        ('{"text": "free text"}', set()),
    ],
)
def test_selected_choice_ids_tolerate_odd_payloads(
    answer_data: str, expected: set[int]
) -> None:
    assert selected_choice_ids(stored_answer(answer_data)) == expected


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        # Unhashable entries used to make set() raise a TypeError.
        ("[[1]]", set()),
        ('[{"id": 1}]', set()),
        ('[1, [2], {"id": 3}, 4]', {1, 4}),
        # Booleans compare equal to ids 0 and 1, and strings never match an id.
        ("[true, false]", set()),
        ('["1", 1.5, null]', set()),
    ],
)
def test_selected_choice_ids_keep_only_integer_ids(
    entries: str, expected: set[int]
) -> None:
    assert (
        selected_choice_ids(stored_answer(f'{{"selected_choice_ids": {entries}}}'))
        == expected
    )


def test_a_corrupted_selection_scores_zero_instead_of_crashing() -> None:
    choices = [choice(1, correct=True, points=1)]
    answer = stored_answer('{"selected_choice_ids": [[1], true]}')
    assert (
        selected_choice_score(
            choices, selected_choice_ids(answer), allow_negative_points=False
        )
        == 0
    )


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    return session_factory_for(settings_for(tmp_path / "edges").database_url)


def add_question(
    session: Session, bank_id: int, answer_mode: str, choices: list[tuple[bool, float]]
) -> int:
    question = Question(
        question_bank_id=bank_id,
        prompt="Prompt",
        difficulty="easy",
        answer_mode=answer_mode,
    )
    session.add(question)
    session.flush()
    session.add_all(
        QuestionChoice(
            question_id=question.id,
            label=f"Choice {position}",
            is_correct=is_correct,
            points=points,
            position=position,
        )
        for position, (is_correct, points) in enumerate(choices)
    )
    session.flush()
    return question.id


def test_question_maximums_follow_the_scoring_rule(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = User(
            username="owner",
            display_name="Owner",
            password_hash=hash_password("an-unused-password-value"),
        )
        session.add(owner)
        session.flush()
        bank = QuestionBank(owner_id=owner.id, grade_level="Tle", chapter="Edges")
        session.add(bank)
        session.flush()
        single = add_question(
            session, bank.id, "single", [(True, 1), (True, 3), (False, 5)]
        )
        multiple = add_question(
            session,
            bank.id,
            "multiple",
            [(True, 1.25), (True, 2), (True, -1), (False, 4)],
        )
        written = add_question(session, bank.id, "written", [])
        only_distractors = add_question(
            session, bank.id, "multiple", [(False, 2), (False, -1)]
        )
        unknown = 10**9

        maximums = question_maximum_scores(
            [single, multiple, written, only_distractors, unknown], session
        )

    # A single-answer question pays its best correct choice, never their sum.
    assert maximums[single] == 3
    # Negative correct choices and priced distractors never raise the ceiling.
    assert maximums[multiple] == 3.25
    assert maximums[written] == 0
    assert maximums[only_distractors] == 0
    assert maximums[unknown] == 0
    assert list(maximums) == [single, multiple, written, only_distractors, unknown]


@pytest.mark.parametrize("stored", [None, "not json", "[1, 2]"])
def test_unreadable_answer_payloads_are_treated_as_empty(stored) -> None:
    assert decoded_answer_data(SimpleNamespace(answer_data=stored)) == {}


class _ScriptedSession:
    def __init__(self, *results: list[Any]) -> None:
        self._results = list(results)

    def scalars(self, _statement: object) -> list[Any]:
        return self._results.pop(0)


def test_final_scores_handle_deleted_and_ungraded_written_questions() -> None:
    deleted = SimpleNamespace(
        question_id=1, answer_data="{}", score=3.0, is_graded=False
    )
    ungraded = SimpleNamespace(
        question_id=2,
        answer_data='{"written_answer": "Because"}',
        score=4.0,
        is_graded=False,
    )
    graded = SimpleNamespace(question_id=2, answer_data="{}", score=4.0, is_graded=True)
    # A skipped written question: blank, so nothing waits for a teacher.
    skipped = SimpleNamespace(
        question_id=2, answer_data="{}", score=4.0, is_graded=False
    )
    # An unreadable row is not a skip: it keeps waiting for a teacher.
    unreadable = SimpleNamespace(
        question_id=2, answer_data="not json", score=4.0, is_graded=False
    )
    written = SimpleNamespace(id=2, answer_mode="written")
    session = _ScriptedSession(
        [deleted, ungraded, graded, skipped, unreadable], [], [written]
    )

    compute_final_scores(SimpleNamespace(id=1, allow_negative_points=False), session)

    assert (deleted.score, deleted.is_graded) == (0, True)
    assert (ungraded.score, ungraded.is_graded) == (0, False)
    assert (graded.score, graded.is_graded) == (4.0, True)
    assert (skipped.score, skipped.is_graded) == (0, True)
    assert (unreadable.score, unreadable.is_graded) == (0, False)


def test_final_scores_without_answers_do_not_load_choices() -> None:
    session = _ScriptedSession([], [])
    compute_final_scores(SimpleNamespace(id=1, allow_negative_points=False), session)
    assert session._results == []

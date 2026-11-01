"""The scoring rule and question maximums, exercised without FastAPI."""

from app.models import QuestionChoice
from app.services.grading import question_maximum_scores, selected_choice_score


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

"""Question draws, exercised without FastAPI, and their HTTP error."""

from pathlib import Path

import pytest

from app.services.question_draws import QuestionDrawPool, draw_unique_question_ids

from support import exam_environment, make_client, settings_for


class _Pool:
    possible_combination_count = 5

    def draw(self) -> list[int]:
        return [1]


def test_unique_draws_fall_back_to_a_repeated_draw() -> None:
    assert draw_unique_question_ids(_Pool(), {(1,)}) == [1]


def test_a_pool_draws_the_requested_count_per_difficulty() -> None:
    pool = QuestionDrawPool(
        {"easy": 2, "medium": 0, "hard": 1},
        {"easy": [1, 2, 3], "hard": [7, 8]},
    )
    assert pool.possible_combination_count == 6
    for _ in range(20):
        drawn = pool.draw()
        assert len(drawn) == 3
        assert len(set(drawn) & {1, 2, 3}) == 2
        assert len(set(drawn) & {7, 8}) == 1


def test_unique_draws_use_every_combination_before_repeating() -> None:
    pool = QuestionDrawPool({"easy": 1}, {"easy": [1, 2, 3]})
    used_draws: set[tuple[int, ...]] = set()
    drawn = [draw_unique_question_ids(pool, used_draws) for _ in range(3)]
    assert sorted(question_id for (question_id,) in drawn) == [1, 2, 3]
    assert used_draws == {(1,), (2,), (3,)}
    assert draw_unique_question_ids(pool, used_draws)[0] in {1, 2, 3}


@pytest.mark.parametrize("difficulty", ["easy", "hard"])
def test_requesting_more_questions_than_the_banks_hold_is_refused(
    tmp_path: Path, difficulty: str
) -> None:
    with make_client(settings_for(tmp_path / "draws")) as client:
        environment = exam_environment(client)
        counts = {"easy_question_count": 1, "medium_question_count": 0}
        counts["hard_question_count"] = 0
        counts[f"{difficulty}_question_count"] = 2
        response = client.post(
            f"/api/quizzes/{environment['quiz']['id']}/update",
            headers=environment["teacher_headers"],
            json={
                "title": "Too many questions",
                "question_bank_ids": [environment["question"]["question_bank_id"]],
                **counts,
            },
        )
        assert response.status_code == 422
        assert response.json() == {
            "detail": (
                "Nombre de questions insuffisant pour une ou plusieurs difficultés "
                "dans les banques sélectionnées"
            )
        }

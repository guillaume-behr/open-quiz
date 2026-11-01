"""Quiz router safeguards for legacy rows, races and dropped connections."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from sqlalchemy import select, text, update
from starlette.websockets import WebSocketDisconnect

from app.models import (
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    QuizSessionStudentQuestion,
    TrainingQuizProfile,
)
from app.routers import live, quizzes, results

from support import (
    FRONTEND_ORIGIN,
    concurrent_writes,
    correct_choice_id,
    exam_environment,
    hand_in_quiz,
    launch_and_join,
    make_client,
    settings_for,
)


@pytest.fixture
def environment(tmp_path: Path):
    with make_client(settings_for(tmp_path / "quiz-edges")) as client:
        environment = exam_environment(client)
        environment["client"] = client
        yield environment


def start(client, environment: dict[str, Any]) -> tuple[dict, dict[str, str], str]:
    launched, participant_headers = launch_and_join(client, environment)
    client.post(
        f"/api/quizzes/sessions/{launched['id']}/start",
        headers=environment["teacher_headers"],
    )
    return (
        launched,
        participant_headers,
        f"/api/quizzes/student/sessions/{launched['join_code']}",
    )


def answer(client, environment, url: str, headers: dict[str, str]):
    return client.post(
        f"{url}/answer",
        headers=headers,
        json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
    )


class _Pool:
    possible_combination_count = 5

    def draw(self) -> list[int]:
        return [1]


def test_unique_draws_fall_back_to_a_repeated_draw() -> None:
    assert quizzes.draw_unique_question_ids(_Pool(), {(1,)}) == [1]


def test_helpers_read_legacy_session_settings() -> None:
    started_at = datetime(2026, 1, 1, 12, 0)
    paused_at = datetime(2026, 1, 1, 12, 5)
    quiz = SimpleNamespace(duration_seconds=600, mode="exam", allow_answer_review=False)
    legacy = SimpleNamespace(
        started_at=started_at,
        paused_duration_seconds=None,
        status="paused",
        paused_at=paused_at,
        duration_seconds=None,
        allow_answer_review=None,
    )
    ends_at = quizzes.quiz_ends_at(legacy, quiz)
    assert ends_at.tzinfo is UTC
    assert ends_at > started_at.replace(tzinfo=UTC) + timedelta(seconds=600)
    assert quizzes.answer_review_enabled(legacy, quiz) is False
    assert quizzes.question_maximum_scores([], session=None) == {}

    missing_class = SimpleNamespace(class_id=1, class_name="Archived class")
    session = SimpleNamespace(get=lambda *_: None)
    assert quizzes.quiz_session_class_name(missing_class, session) == "Archived class"


class _Answers:
    def __init__(self, answers: list[Any]) -> None:
        self.answers = answers

    def scalars(self, _statement: object) -> list[Any]:
        return self.answers


def test_summaries_and_training_results_skip_missing_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written = SimpleNamespace(id=1, answer_mode="written")
    choice = SimpleNamespace(
        id=2, answer_mode="single", answer_mode_disclosed=True, prompt="Pick"
    )
    answers = [SimpleNamespace(question_id=2, answer_data="{}")]
    monkeypatch.setattr(
        quizzes,
        "load_question_records",
        lambda *_: ({1: written, 2: choice}, {1: [], 2: []}),
    )
    monkeypatch.setattr(quizzes, "question_maximum_scores", lambda *_: {2: 1.0})
    quiz_session = SimpleNamespace(id=1)
    participant = SimpleNamespace(id=1)

    summaries = quizzes.student_answer_summaries(
        quiz_session, participant, [3, 1, 2], _Answers(answers)
    )
    assert [summary.question_id for summary in summaries] == [2]

    monkeypatch.setattr(quizzes, "session_question_ids", lambda *_: [3, 1, 2])
    assert quizzes.training_result(quiz_session, participant, _Answers(answers)) == (
        0.0,
        1.0,
        0,
    )
    monkeypatch.setattr(quizzes, "session_question_ids", lambda *_: [])
    assert quizzes.training_result(quiz_session, participant, _Answers([])) == (
        0.0,
        0.0,
        0,
    )


def test_missing_questions_are_reported_instead_of_crashing(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    _, headers, url = start(client, environment)
    monkeypatch.setattr(quizzes, "load_question_records", lambda *_: ({}, {}))
    assert client.get(url, headers=headers).status_code == 409
    assert answer(client, environment, url, headers).status_code == 409


def test_results_cover_common_draws_and_silent_participants(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    common = client.post(
        f"/api/quizzes/{environment['quiz']['id']}/update",
        headers=headers,
        json={
            "title": "Common draw",
            "question_bank_ids": [environment["question"]["question_bank_id"]],
            "same_questions_for_all": True,
            "easy_question_count": 1,
            "medium_question_count": 0,
            "hard_question_count": 0,
        },
    )
    assert common.status_code == 200
    launched, participant_headers, url = start(client, environment)
    assert client.post(f"{url}/leave", headers=participant_headers).status_code == 204
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(status="finished")
        )
        participant_id = session.scalar(
            select(QuizParticipant.id).where(
                QuizParticipant.session_id == launched["id"]
            )
        )
        session.commit()

    results = client.get("/api/quizzes/sessions/results", headers=headers).json()
    assert results[0]["total_questions"] == 1
    silent = client.get(
        f"/api/quizzes/sessions/{launched['id']}/participants/{participant_id}/answers",
        headers=headers,
    )
    assert silent.status_code == 200
    assert silent.json() == []

    # A participant who left before the start is not part of the results.
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizParticipant)
            .where(QuizParticipant.id == participant_id)
            .values(left_at=datetime(2000, 1, 1, tzinfo=UTC))
        )
        session.commit()
    export = client.get(
        "/api/quizzes/sessions/results/export",
        headers=headers,
        params={"class_id": environment["student_class"]["id"]},
    )
    assert export.status_code == 200
    assert len(export.text.strip().splitlines()) == 1


def test_teacher_session_view_reads_draws_by_identifier(environment) -> None:
    client = environment["client"]
    launched, headers, url = start(client, environment)
    assert answer(client, environment, url, headers).status_code == 200
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSessionStudentQuestion)
            .where(QuizSessionStudentQuestion.session_id == launched["id"])
            .values(student_id=None)
        )
        session.commit()
    state = client.get(
        f"/api/quizzes/sessions/{launched['id']}",
        headers=environment["teacher_headers"],
    ).json()
    assert state["participants"][0]["maximum_score"] == 2


def test_review_summaries_tolerate_corrupted_answers(environment) -> None:
    client = environment["client"]
    launched, headers, url = start(client, environment)
    assert answer(client, environment, url, headers).status_code == 200
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizAnswer)
            .where(QuizAnswer.session_id == launched["id"])
            .values(answer_data=json.dumps({"selected_choice_ids": "corrupted"}))
        )
        session.commit()
    state = client.get(url, headers=headers).json()
    assert state["answer_summaries"][0]["submitted_answers"] == []


def test_a_concurrent_finish_is_not_applied_twice(environment) -> None:
    client = environment["client"]
    launched, headers, url = start(client, environment)
    assert answer(client, environment, url, headers).status_code == 200
    with concurrent_writes(
        client,
        (
            "UPDATE quiz_sessions SET status",
            lambda connection: connection.execute(
                update(QuizSession)
                .where(QuizSession.id == launched["id"])
                .values(status="finished")
            ),
        ),
    ) as fired:
        hand_in_quiz(client, launched["join_code"], headers)
    assert fired
    # The concurrent request already closed the session, so this one left it.
    with client.app.state.session_factory() as session:
        assert session.get(QuizSession, launched["id"]).status == "finished"


def test_grading_rejects_answers_outside_the_participant_draw(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    launched, participant_headers, url = start(client, environment)
    assert answer(client, environment, url, participant_headers).status_code == 200
    hand_in_quiz(client, launched["join_code"], participant_headers)
    other = client.post(
        f"/api/question-banks/{environment['question']['question_bank_id']}/questions",
        headers=headers,
        data={
            "payload": json.dumps(
                {
                    "prompt": "Explain",
                    "difficulty": "hard",
                    "answer_mode": "written",
                    "choices": [{"label": "Because", "is_correct": True}],
                }
            )
        },
    ).json()
    with client.app.state.session_factory() as session:
        participant_id = session.scalar(
            select(QuizParticipant.id).where(
                QuizParticipant.session_id == launched["id"]
            )
        )
        stray = QuizAnswer(
            session_id=launched["id"],
            participant_id=participant_id,
            question_id=other["id"],
            answer_data=json.dumps({"written_answer": "Stray"}),
        )
        session.add(stray)
        session.commit()
        stray_id = stray.id
    response = client.post(
        f"/api/quizzes/sessions/{launched['id']}/answers/{stray_id}/grade",
        headers=headers,
        json={"score": 1},
    )
    assert response.status_code == 409


def test_student_history_skips_questions_it_cannot_load(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    launched, headers, url = start(client, environment)
    assert answer(client, environment, url, headers).status_code == 200
    hand_in_quiz(client, launched["join_code"], headers)
    client.post(
        f"/api/quizzes/sessions/{launched['id']}/publish-grades",
        headers=environment["teacher_headers"],
    )
    monkeypatch.setattr(results, "load_question_records", lambda *_: ({}, {}))
    history = client.get(
        "/api/quizzes/student/results", headers=environment["student_headers"]
    ).json()
    assert history[0]["answers"] == []


def test_training_profile_conflicts_are_not_hidden(environment) -> None:
    client = environment["client"]
    headers = environment["teacher_headers"]
    class_id = environment["student_class"]["id"]
    bank_id = environment["question"]["question_bank_id"]
    teacher_id = client.get("/api/users/me", headers=headers).json()["id"]
    client.put(
        f"/api/quizzes/training/classes/{class_id}/question-banks",
        headers=headers,
        json={"question_bank_ids": [bank_id]},
    )

    def claim_profile(connection) -> None:
        connection.execute(
            text(
                "INSERT INTO training_quiz_profiles (owner_id, quiz_id) "
                "SELECT :owner_id, id FROM quizzes WHERE owner_id = :owner_id "
                "AND mode = 'exam' LIMIT 1"
            ),
            {"owner_id": teacher_id},
        )

    def release_profile(connection) -> None:
        connection.execute(
            TrainingQuizProfile.__table__.delete().where(
                TrainingQuizProfile.owner_id == teacher_id
            )
        )

    with (
        concurrent_writes(
            client,
            ("INSERT INTO training_quiz_profiles", claim_profile),
            ("SELECT quizzes", release_profile),
        ) as fired,
        pytest.raises(Exception, match="training_quiz_profiles"),
    ):
        client.post(
            f"/api/quizzes/training/{bank_id}/start",
            headers=environment["student_headers"],
        )
    assert len(fired) == 2


def test_live_feeds_keep_quiet_and_stop_on_disconnect(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    monkeypatch.setattr(live, "LIVE_TEACHER_RECONCILIATION_SECONDS", 0.01)
    monkeypatch.setattr(live, "LIVE_HEARTBEAT_SECONDS", 0.01)
    monkeypatch.setattr(live.LiveHeartbeat, "is_due", lambda self: True)
    launched, participant_headers = launch_and_join(client, environment)
    teacher_token = {
        "token": environment["teacher_headers"]["Authorization"].removeprefix("Bearer ")
    }
    feeds = [
        ("/api/quizzes/live/teacher/sessions", teacher_token),
        (f"/api/quizzes/live/teacher/sessions/{launched['id']}", teacher_token),
        (
            f"/api/quizzes/live/student/sessions/{launched['join_code']}",
            {"token": participant_headers["X-Quiz-Token"]},
        ),
        ("/api/quizzes/live/teacher/makeup-sessions", teacher_token),
    ]
    for path, credentials in feeds:
        with client.websocket_connect(path, headers={"Origin": FRONTEND_ORIGIN}) as (
            socket
        ):
            socket.send_json(credentials)
            assert socket.receive_json()["type"] != "ping"
            # A second and third round find nothing new and only ping.
            assert socket.receive_json() == {"type": "ping"}
            assert socket.receive_json() == {"type": "ping"}

    async def dropped(*_: object, **__: object) -> None:
        raise WebSocketDisconnect(1006)

    monkeypatch.setattr(live, "wait_for_live_update", dropped)
    for path, credentials in feeds:
        with client.websocket_connect(path, headers={"Origin": FRONTEND_ORIGIN}) as (
            socket
        ):
            socket.send_json(credentials)
            # The feed stops on its own once the connection drops: leaving the
            # block only waits for the endpoint to return.
            assert socket.receive_json()["type"] != "ping"


def test_an_expiry_already_applied_elsewhere_is_reloaded(environment) -> None:
    client = environment["client"]
    launched, _, _ = start(client, environment)
    with client.app.state.session_factory() as session:
        session.execute(
            update(QuizSession)
            .where(QuizSession.id == launched["id"])
            .values(started_at=datetime.now(UTC) - timedelta(hours=2))
        )
        session.commit()
    with concurrent_writes(
        client,
        (
            "UPDATE quiz_sessions SET status",
            lambda connection: connection.execute(
                update(QuizSession)
                .where(QuizSession.id == launched["id"])
                .values(status="finished")
            ),
        ),
    ) as fired:
        state = client.get(
            f"/api/quizzes/sessions/{launched['id']}",
            headers=environment["teacher_headers"],
        )
    assert fired
    assert state.json()["status"] == "finished"


def test_makeup_feed_waits_for_its_heartbeat(
    environment, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = environment["client"]
    monkeypatch.setattr(live, "LIVE_TEACHER_RECONCILIATION_SECONDS", 0.01)
    due = iter([False, False])
    monkeypatch.setattr(live.LiveHeartbeat, "is_due", lambda self: next(due, True))
    token = environment["teacher_headers"]["Authorization"].removeprefix("Bearer ")
    with client.websocket_connect(
        "/api/quizzes/live/teacher/makeup-sessions",
        headers={"Origin": FRONTEND_ORIGIN},
    ) as socket:
        socket.send_json({"token": token})
        assert socket.receive_json() == {"type": "makeup_sessions", "data": []}
        assert socket.receive_json() == {"type": "ping"}

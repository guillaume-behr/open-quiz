"""The expiry loop: sessions end on time without anybody reading them."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

import main
from app.database import EXPIRY_LOCK_KEY
from app.models import QuizSession

from support import (
    correct_choice_id,
    exam_environment,
    launch_and_join,
    make_client,
    settings_for,
)


def test_a_tick_skips_while_another_worker_holds_the_lock(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "expiry-lock")) as client:
        environment = exam_environment(client)
        launched, _ = launch_and_join(client, environment)
        client.post(
            f"/api/quizzes/sessions/{launched['id']}/start",
            headers=environment["teacher_headers"],
        )
        session_factory = client.app.state.session_factory
        with session_factory() as session:
            session.execute(
                update(QuizSession)
                .where(QuizSession.id == launched["id"])
                .values(started_at=datetime.now(UTC) - timedelta(hours=2))
            )
            session.commit()

        hub = client.app.state.live_quiz_hub
        with session_factory() as other_worker:
            assert other_worker.scalar(
                select(func.pg_try_advisory_xact_lock(EXPIRY_LOCK_KEY))
            )
            assert main.expire_due_sessions(session_factory, hub) == 0
        assert main.expire_due_sessions(session_factory, hub) == 1
        assert main.expire_due_sessions(session_factory, hub) == 0


def test_the_loop_retries_after_a_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ticks: list[str] = []

    async def short_sleep(_: float) -> None:
        if len(ticks) == 2:
            raise asyncio.CancelledError

    def expire(*_: object) -> int:
        ticks.append("tick")
        if len(ticks) == 1:
            raise OperationalError("SELECT 1", {}, Exception("database is down"))
        return 0

    logged: list[str] = []
    monkeypatch.setattr(main, "sleep", short_sleep)
    monkeypatch.setattr(main, "expire_due_sessions", expire)
    monkeypatch.setattr(main.logger, "exception", logged.append)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main.expire_sessions_periodically(None, None))
    assert ticks == ["tick", "tick"]
    assert logged == ["Session expiry failed"]


def test_an_answer_after_the_deadline_finishes_the_session_first(
    tmp_path: Path,
) -> None:
    """Writes do not wait for the loop: a late answer is refused at once."""
    with make_client(settings_for(tmp_path / "expiry-write")) as client:
        environment = exam_environment(client)
        launched, participant_headers = launch_and_join(client, environment)
        client.post(
            f"/api/quizzes/sessions/{launched['id']}/start",
            headers=environment["teacher_headers"],
        )
        with client.app.state.session_factory() as session:
            session.execute(
                update(QuizSession)
                .where(QuizSession.id == launched["id"])
                .values(started_at=datetime.now(UTC) - timedelta(hours=2))
            )
            session.commit()

        late = client.post(
            f"/api/quizzes/student/sessions/{launched['join_code']}/answer",
            headers=participant_headers,
            json={"selected_choice_ids": [correct_choice_id(environment["question"])]},
        )
        assert late.status_code == 409
        assert late.json()["detail"]["code"] == "QUIZ_NO_CURRENT_QUESTION"
        state = client.get(
            f"/api/quizzes/sessions/{launched['id']}",
            headers=environment["teacher_headers"],
        )
        assert state.json()["status"] == "finished"

"""The expiry loop: sessions end on time without anybody reading them."""

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.exc import OperationalError

from app import application
from app.core.database import EXPIRY_LOCK_KEY
from app.models import QuizSession, User
from app.services import maintenance, session_lifecycle

from support import (
    choice_answer,
    correct_choice_id,
    exam_environment,
    expire_due_sessions,
    launch_and_join,
    make_client,
    seeded_exam_session,
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
            assert maintenance.expire_due_sessions(session_factory, hub) == 0
        assert maintenance.expire_due_sessions(session_factory, hub) == 1
        assert maintenance.expire_due_sessions(session_factory, hub) == 0


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
    monkeypatch.setattr(maintenance, "sleep", short_sleep)
    monkeypatch.setattr(maintenance, "expire_due_sessions", expire)
    monkeypatch.setattr(maintenance.logger, "exception", logged.append)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(maintenance.expire_sessions_periodically(None, None))
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
            json=choice_answer(
                client, participant_headers, correct_choice_id(environment["question"])
            ),
        )
        assert late.status_code == 409
        assert late.json()["detail"]["code"] == "QUIZ_NO_CURRENT_QUESTION"
        state = client.get(
            f"/api/quizzes/sessions/{launched['id']}",
            headers=environment["teacher_headers"],
        )
        assert state.json()["status"] == "finished"


def test_retention_maintenance_retries_after_a_database_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runs: list[str] = []

    async def short_sleep(_: float) -> None:
        if len(runs) == 2:
            raise asyncio.CancelledError

    def enforce(*_: object) -> None:
        runs.append("run")
        if len(runs) == 1:
            raise OperationalError("SELECT 1", {}, Exception("database is down"))

    logged: list[str] = []
    monkeypatch.setattr(maintenance, "sleep", short_sleep)
    monkeypatch.setattr(maintenance, "enforce_data_retention", enforce)
    monkeypatch.setattr(maintenance.logger, "exception", logged.append)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(maintenance.maintain_data_retention_periodically(None, None))
    assert runs == ["run", "run"]
    assert logged == ["Data retention maintenance failed"]


@pytest.mark.parametrize(
    ("loop", "work", "message"),
    [
        (
            "expire_sessions_periodically",
            "expire_due_sessions",
            "Session expiry failed",
        ),
        (
            "maintain_data_retention_periodically",
            "enforce_data_retention",
            "Data retention maintenance failed",
        ),
    ],
)
def test_the_loops_survive_any_exception(
    monkeypatch: pytest.MonkeyPatch, loop: str, work: str, message: str
) -> None:
    """A bug in one run must not stop expiry or retention until a restart."""
    runs: list[str] = []

    async def short_sleep(_: float) -> None:
        if len(runs) == 2:
            raise asyncio.CancelledError

    def run_once(*_: object) -> int:
        runs.append("run")
        if len(runs) == 1:
            raise RuntimeError("unexpected")
        return 0

    logged: list[str] = []
    monkeypatch.setattr(maintenance, "sleep", short_sleep)
    monkeypatch.setattr(maintenance, work, run_once)
    monkeypatch.setattr(maintenance.logger, "exception", logged.append)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(getattr(maintenance, loop)(None, None))
    assert runs == ["run", "run"]
    assert logged == [message]


def test_a_failing_session_does_not_hold_back_the_other_due_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(settings_for(tmp_path / "expiry-isolation")) as client:
        factory = client.app.state.session_factory
        long_ago = datetime.now(UTC) - timedelta(hours=2)
        with factory() as session:
            admin = session.scalar(select(User).where(User.is_admin.is_(True)))
            assert admin is not None
            broken_id, healthy_id = (
                seeded_exam_session(
                    session,
                    admin.id,
                    join_code=join_code,
                    status_value="in_progress",
                    created_at=long_ago,
                    with_answer=True,
                )
                for join_code in ("BROKEN1", "HEALTH1")
            )
            # Still running and not due yet: a tick leaves it alone.
            running_id = seeded_exam_session(
                session,
                admin.id,
                join_code="RUNNIN1",
                status_value="in_progress",
                created_at=datetime.now(UTC),
                with_answer=True,
            )
            session.commit()

        finish_session = session_lifecycle.finish_session

        def finish_unless_broken(quiz_session, quiz, session, *args) -> bool:
            if quiz_session.id == broken_id:
                raise RuntimeError("cannot grade this session")
            return finish_session(quiz_session, quiz, session, *args)

        logged: list[tuple[object, ...]] = []
        monkeypatch.setattr(session_lifecycle, "finish_session", finish_unless_broken)
        monkeypatch.setattr(
            session_lifecycle.logger,
            "exception",
            lambda *args, **_: logged.append(args),
        )
        assert expire_due_sessions(client) == 1

        with factory() as session:
            assert session.get(QuizSession, healthy_id).status == "finished"
            assert session.get(QuizSession, broken_id).status == "in_progress"
            assert session.get(QuizSession, running_id).status == "in_progress"
        assert logged == [("Finishing expired session %s failed", broken_id)]


def test_shutdown_does_not_raise_what_a_background_task_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def crash(*_: object) -> None:
        raise RuntimeError("background task crashed")

    logged: list[tuple[object, ...]] = []
    monkeypatch.setattr(application, "expire_sessions_periodically", crash)
    monkeypatch.setattr(
        application.logger, "exception", lambda *args, **_: logged.append(args)
    )
    with make_client(settings_for(tmp_path / "crashed-task")) as client:
        # Let the crashed task finish before shutting down.
        assert client.get("/api/health").status_code == 200
    assert logged == [("Background task %s failed", "session expiry")]


def test_a_tick_skips_a_session_another_request_holds(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "expiry-race")) as client:
        factory = client.app.state.session_factory
        with factory() as session:
            admin = session.scalar(select(User).where(User.is_admin.is_(True)))
            assert admin is not None
            raced_id = seeded_exam_session(
                session,
                admin.id,
                join_code="RACED02",
                status_value="in_progress",
                created_at=datetime.now(UTC) - timedelta(hours=2),
                with_answer=True,
            )
            session.commit()

        # A request working on the session (an answer being saved) holds its
        # row: the tick does not wait for it, and the next one finishes it.
        with factory() as holder:
            holder.execute(
                select(QuizSession).where(QuizSession.id == raced_id).with_for_update()
            )
            assert expire_due_sessions(client) == 0
        assert expire_due_sessions(client) == 1

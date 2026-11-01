"""Data retention: purges, released join codes and abandoned sessions."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import time

from fastapi.testclient import TestClient
from sqlalchemy import select

import main
from app.models import (
    AuthenticationChallenge,
    ProblemReport,
    Quiz,
    QuizAnswer,
    QuizJoinCode,
    QuizParticipant,
    QuizSession,
    RefreshSession,
    RefreshSessionFamily,
    User,
)
from main import create_app

from support import (
    FRONTEND_ORIGIN,
    TEST_CLIENT_BACKEND_OPTIONS,
    exam_environment,
    make_client,
    seeded_exam_session,
    settings_for,
)


def test_startup_enforces_security_data_retention(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "retention",
        quiz_result_retention_days=1,
        problem_report_retention_days=1,
    )
    app = create_app(settings)
    with TestClient(
        app,
        headers={"Origin": FRONTEND_ORIGIN},
        backend_options=TEST_CLIENT_BACKEND_OPTIONS,
    ):
        pass

    expired_at = datetime.now(UTC) - timedelta(days=2)
    with app.state.session_factory() as session:
        admin = session.scalar(select(User).where(User.is_admin.is_(True)))
        assert admin is not None
        quiz = Quiz(
            owner_id=admin.id,
            title="Expired quiz",
            question_count=1,
            easy_question_count=1,
            medium_question_count=0,
            hard_question_count=0,
        )
        session.add(quiz)
        session.flush()
        quiz_session = QuizSession(
            quiz_id=quiz.id,
            class_name="Expired class",
            join_code="OLD123",
            status="finished",
            started_at=expired_at,
        )
        session.add(quiz_session)
        session.flush()
        session.add(
            QuizParticipant(
                session_id=quiz_session.id,
                student_identifier="expired.student",
            )
        )
        session.add(
            ProblemReport(
                message="Expired report",
                page_path="/",
                created_at=expired_at,
            )
        )
        refresh_session = RefreshSession(
            token_hash="a" * 64,
            user_id=admin.id,
            expires_at=int(time()) - 1,
        )
        session.add(refresh_session)
        session.flush()
        session.add(
            RefreshSessionFamily(
                session_id=refresh_session.id,
                family_id="b" * 64,
            )
        )
        session.add(
            AuthenticationChallenge(
                token_id_hash="c" * 64,
                user_id=admin.id,
                purpose="two_factor_verification",
                expires_at=int(time()) - 1,
            )
        )
        session.commit()

    with make_client(settings):
        pass

    with app.state.session_factory() as session:
        for model in (
            QuizSession,
            QuizParticipant,
            ProblemReport,
            RefreshSession,
            RefreshSessionFamily,
            AuthenticationChallenge,
        ):
            assert session.query(model).count() == 0


def test_retention_settles_sessions_their_teacher_never_closed(
    tmp_path: Path,
) -> None:
    """A session only expires when its owner signs in; retention cannot wait."""
    settings = settings_for(
        tmp_path / "abandoned-sessions",
        abandoned_session_retention_days=7,
    )
    app = create_app(settings)
    with make_client(settings):
        pass

    abandoned_at = datetime.now(UTC) - timedelta(days=10)
    with app.state.session_factory() as session:
        admin = session.scalar(select(User).where(User.is_admin.is_(True)))
        assert admin is not None
        graded_id = seeded_exam_session(
            session,
            admin.id,
            join_code="GRADED1",
            status_value="in_progress",
            created_at=abandoned_at,
            with_answer=True,
        )
        empty_id = seeded_exam_session(
            session,
            admin.id,
            join_code="EMPTY01",
            status_value="waiting",
            created_at=abandoned_at,
            with_answer=False,
        )
        recent_id = seeded_exam_session(
            session,
            admin.id,
            join_code="RECENT1",
            status_value="in_progress",
            created_at=datetime.now(UTC),
            with_answer=True,
        )
        session.commit()

    main.enforce_data_retention(app.state.session_factory, settings)

    with app.state.session_factory() as session:
        graded = session.get(QuizSession, graded_id)
        assert graded is not None
        assert graded.status == "finished"
        answer = session.scalar(
            select(QuizAnswer).where(QuizAnswer.session_id == graded_id)
        )
        assert answer is not None
        assert answer.is_graded
        assert answer.score == 2.0
        participant = session.scalar(
            select(QuizParticipant).where(QuizParticipant.session_id == graded_id)
        )
        assert participant is not None
        assert participant.current_position is None

        # A waiting room nobody used holds names and nothing to grade.
        assert session.get(QuizSession, empty_id) is None
        assert (
            session.scalar(
                select(QuizParticipant).where(QuizParticipant.session_id == empty_id)
            )
            is None
        )

        recent = session.get(QuizSession, recent_id)
        assert recent is not None
        assert recent.status == "in_progress"


def test_retention_purges_finished_training_attempts(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "training-retention",
        training_result_retention_days=30,
    )
    app = create_app(settings)
    with make_client(settings):
        pass

    with app.state.session_factory() as session:
        admin = session.scalar(select(User).where(User.is_admin.is_(True)))
        assert admin is not None
        quiz = Quiz(
            owner_id=admin.id,
            mode="training",
            title="Training quiz",
            question_count=1,
        )
        session.add(quiz)
        session.flush()
        expired = QuizSession(
            quiz_id=quiz.id,
            class_name="Training class",
            join_code="TRAIN01",
            status="finished",
            created_at=datetime.now(UTC) - timedelta(days=45),
        )
        kept = QuizSession(
            quiz_id=quiz.id,
            class_name="Training class",
            join_code="TRAIN02",
            status="finished",
            created_at=datetime.now(UTC) - timedelta(days=5),
        )
        session.add_all([expired, kept])
        session.flush()
        session.add(
            QuizParticipant(
                session_id=expired.id,
                student_identifier="pupil.training",
                student_display_name="Training Pupil",
            )
        )
        expired_id, kept_id = expired.id, kept.id
        session.commit()

    main.enforce_data_retention(app.state.session_factory, settings)

    with app.state.session_factory() as session:
        assert session.get(QuizSession, expired_id) is None
        assert (
            session.scalar(
                select(QuizParticipant).where(QuizParticipant.session_id == expired_id)
            )
            is None
        )
        assert session.get(QuizSession, kept_id) is not None


def test_discarded_sessions_release_their_join_codes(tmp_path: Path) -> None:
    """A join code is reserved for the life of its session, not forever.

    Restarting training discards the previous attempt, so a student who keeps
    restarting would otherwise burn one row of the reservation table per
    attempt, with nothing in the retention sweep to reclaim it.
    """
    with make_client(settings_for(tmp_path / "join-code-release.db")) as client:
        environment = exam_environment(client)
        bank_id = environment["question"]["question_bank_id"]
        assert (
            client.put(
                f"/api/quizzes/training/classes/"
                f"{environment['student_class']['id']}/question-banks",
                headers=environment["teacher_headers"],
                json={"question_bank_ids": [bank_id]},
            ).status_code
            == 200
        )
        for _ in range(4):
            assert (
                client.post(
                    f"/api/quizzes/training/{bank_id}/start",
                    headers=environment["student_headers"],
                ).status_code
                == 201
            )

        with client.app.state.session_factory() as session:
            live_codes = set(session.scalars(select(QuizSession.join_code)))
            reserved_codes = set(session.scalars(select(QuizJoinCode.code)))
        assert reserved_codes == live_codes

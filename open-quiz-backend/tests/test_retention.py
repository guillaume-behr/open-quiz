"""Data retention: purges, released join codes and abandoned sessions."""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import time

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app import maintenance
from app.application import create_app
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

from support import (
    FRONTEND_ORIGIN,
    TEST_CLIENT_BACKEND_OPTIONS,
    create_professor,
    exam_environment,
    login_admin,
    make_client,
    seeded_exam_session,
    settings_for,
    training_banks,
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

    maintenance.enforce_data_retention(app.state.session_factory, settings)

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

    maintenance.enforce_data_retention(app.state.session_factory, settings)

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
                json=training_banks(bank_id),
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


def test_retention_runs_as_of_the_instant_it_is_given(tmp_path: Path) -> None:
    """Every cutoff derives from one ``now``, which tests can set directly."""
    settings = settings_for(
        tmp_path / "retention-instant",
        quiz_result_retention_days=30,
    )
    with make_client(settings) as client:
        professor, _ = create_professor(client, login_admin(client))
        with client.app.state.session_factory() as session:
            recent_id = seeded_exam_session(
                session,
                professor["id"],
                join_code="NOW001",
                status_value="finished",
                created_at=datetime.now(UTC) - timedelta(days=5),
                with_answer=True,
            )
            session.commit()

        factory = client.app.state.session_factory
        maintenance.enforce_data_retention(factory, settings)
        with factory() as session:
            assert session.get(QuizSession, recent_id) is not None

        later = datetime.now(UTC) + timedelta(days=30)
        maintenance.enforce_data_retention(factory, settings, now=later)
        with factory() as session:
            assert session.get(QuizSession, recent_id) is None


def test_results_hide_expired_exams_without_deleting_them(tmp_path: Path) -> None:
    """Reading results never writes: maintenance alone deletes expired ones."""
    settings = settings_for(
        tmp_path / "results-retention",
        quiz_result_retention_days=30,
    )
    with make_client(settings) as client:
        professor, headers = create_professor(client, login_admin(client))
        student_class = client.post(
            "/api/classes",
            headers=headers,
            json={"name": "5e B", "grade_level": "5e"},
        ).json()
        with client.app.state.session_factory() as session:
            session_ids = {
                join_code: seeded_exam_session(
                    session,
                    professor["id"],
                    join_code=join_code,
                    status_value="finished",
                    created_at=datetime.now(UTC) - timedelta(days=age),
                    with_answer=True,
                )
                for join_code, age in (("OLD001", 45), ("NEW001", 5))
            }
            session.execute(
                update(QuizSession)
                .where(QuizSession.id.in_(session_ids.values()))
                .values(class_id=student_class["id"])
            )
            session.commit()

        listed = client.get("/api/quizzes/sessions/results", headers=headers)
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [session_ids["NEW001"]]
        assert listed.headers["X-Total-Count"] == "1"

        exported = client.get(
            "/api/quizzes/sessions/results/export",
            headers=headers,
            params={"class_id": student_class["id"]},
        )
        assert exported.status_code == 200
        assert "Quiz NEW001" in exported.text
        assert "Quiz OLD001" not in exported.text

        with client.app.state.session_factory() as session:
            assert session.get(QuizSession, session_ids["OLD001"]) is not None

        maintenance.enforce_data_retention(client.app.state.session_factory, settings)
        with client.app.state.session_factory() as session:
            assert session.get(QuizSession, session_ids["OLD001"]) is None
            assert session.get(QuizSession, session_ids["NEW001"]) is not None

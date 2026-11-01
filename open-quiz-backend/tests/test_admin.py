"""Administration: teacher accounts, the managed administrator and problem reports."""

from datetime import UTC, datetime
from pathlib import Path
from time import time

import pyotp
import pytest
from fastapi import status
from sqlalchemy import select

from app.models import (
    QuestionBank,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    RefreshSession,
    Student,
    StudentAccount,
    StudentClass,
    User,
)
from app.routers.auth import REFRESH_COOKIE, REFRESH_PROOF_HEADER
from app.security import (
    refresh_request_proof,
)

from support import (
    ADMIN_PASSWORD,
    JWT_SECRET,
    complete_first_login,
    database_connection,
    login_admin,
    make_client,
    seeded_exam_session,
    settings_for,
)


def test_problem_reports_are_anonymous_and_admin_only(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "problem-reports.db")) as client:
        created = client.post(
            "/api/problem-reports",
            json={
                "message": "  Le bouton de validation ne répond pas.  ",
                "page_path": "/dashboard",
            },
        )
        assert created.status_code == 201
        assert created.json()["message"] == ("Le bouton de validation ne répond pas.")
        assert set(created.json()) == {
            "id",
            "message",
            "page_path",
            "created_at",
        }
        assert client.get("/api/problem-reports").status_code == 401

        headers = login_admin(client)
        reports = client.get("/api/problem-reports", headers=headers)
        assert reports.status_code == 200
        assert [report["id"] for report in reports.json()] == [created.json()["id"]]

        deleted = client.delete(
            f"/api/problem-reports/{created.json()['id']}",
            headers=headers,
        )
        assert deleted.status_code == 204
        assert client.get("/api/problem-reports", headers=headers).json() == []


def test_problem_reports_are_rate_limited(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "problem-report-rate-limit.db",
        problem_report_attempts=2,
    )
    with make_client(settings) as client:
        for index in range(2):
            response = client.post(
                "/api/problem-reports",
                json={
                    "message": f"Problème numéro {index}",
                    "page_path": "/",
                },
            )
            assert response.status_code == 201

        limited = client.post(
            "/api/problem-reports",
            json={"message": "Un autre problème", "page_path": "/"},
        )
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) > 0


@pytest.mark.parametrize(
    "page_path",
    ["https://example.test/page", "//example.test/page", "/valid\nspoofed"],
)
def test_problem_reports_reject_non_local_page_paths(
    tmp_path: Path, page_path: str
) -> None:
    with make_client(settings_for(tmp_path / "problem-report-path.db")) as client:
        response = client.post(
            "/api/problem-reports",
            json={"message": "A sufficiently detailed problem", "page_path": page_path},
        )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_admin_routes_require_authentication(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        assert client.get("/api/admin/users").status_code == 401


def test_environment_password_rotation_updates_existing_admin(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    with make_client(settings_for(database)) as client:
        access_headers, _ = complete_first_login(
            client,
            "root-admin",
            ADMIN_PASSWORD,
        )
        previous_refresh = client.cookies.get(REFRESH_COOKIE)
        assert previous_refresh

    rotated = settings_for(
        database,
        admin_password="a-different-strong-password",
    )
    with make_client(rotated) as client:
        assert client.get("/api/users/me", headers=access_headers).status_code == 401
        client.cookies.set(
            REFRESH_COOKIE,
            previous_refresh,
            domain="testserver.local",
            path="/api/auth",
        )
        assert (
            client.post(
                "/api/auth/refresh",
                headers={
                    REFRESH_PROOF_HEADER: refresh_request_proof(
                        previous_refresh,
                        JWT_SECRET,
                    )
                },
            ).status_code
            == 401
        )
        old_login = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        new_login = client.post(
            "/api/auth/login",
            json={
                "username": "root-admin",
                "password": "a-different-strong-password",
            },
        )
        assert old_login.status_code == 401
        assert new_login.status_code == 200


def test_environment_admin_rename_moves_managed_account(tmp_path: Path) -> None:
    database = tmp_path / "test.db"
    with make_client(settings_for(database)) as client:
        headers, secret = complete_first_login(
            client,
            "root-admin",
            ADMIN_PASSWORD,
        )
        original = client.get("/api/users/me", headers=headers).json()

    renamed = settings_for(database, admin_username="renamed-admin")
    with make_client(renamed) as client:
        old_login = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )
        new_login = client.post(
            "/api/auth/login",
            json={"username": "renamed-admin", "password": ADMIN_PASSWORD},
        )
        assert old_login.status_code == 401
        assert new_login.status_code == 200
        verified = client.post(
            "/api/auth/2fa/verify",
            json={
                "challenge_token": new_login.json()["challenge_token"],
                "code": pyotp.TOTP(secret).at(time() + 30),
            },
        )
        renamed_user = client.get(
            "/api/users/me",
            headers={"Authorization": f"Bearer {verified.json()['access_token']}"},
        ).json()
        assert renamed_user["id"] == original["id"]
        assert renamed_user["username"] == "renamed-admin"


def test_problem_report_rate_limit_is_instance_wide(tmp_path: Path) -> None:
    settings = settings_for(
        tmp_path / "problem-report-instance-limit.db",
        problem_report_attempts=2,
    )
    with make_client(settings) as client:
        for index in range(2):
            response = client.post(
                "/api/problem-reports",
                json={"message": f"Problème numéro {index}", "page_path": "/"},
                headers={"X-Forwarded-For": f"203.0.113.{index + 1}"},
            )
            assert response.status_code == 201

        # A fresh client address must not grant a fresh budget: the quota is
        # never keyed on an IP address.
        limited = client.post(
            "/api/problem-reports",
            json={"message": "Encore un problème", "page_path": "/"},
            headers={"X-Forwarded-For": "198.51.100.99"},
        )
        assert limited.status_code == 429


def test_startup_refuses_to_choose_between_unmanaged_administrators(
    tmp_path: Path,
) -> None:
    """Adopting the wrong account would hand the instance to the wrong person.

    Before managed state existed an instance could hold several
    administrators. Startup adopts a single one silently, but with more than
    one and no configured match it must stop rather than guess.
    """
    database = tmp_path / "several-admins.db"
    with make_client(settings_for(database)):
        pass

    with database_connection(database) as connection:
        # Forget which account is managed and rename the existing one, so no
        # administrator matches ADMIN_USERNAME any more.
        connection.execute(
            "DELETE FROM security_state WHERE key = 'managed_admin_user_id'"
        )
        connection.execute(
            "UPDATE users SET username = 'legacy-admin' WHERE username = 'root-admin'"
        )
        connection.execute(
            "INSERT INTO users (username, display_name, password_hash,"
            " access_token_generation, is_admin, is_active, created_at)"
            " VALUES ('second-admin', 'Second', 'x', 0, true, true, now())"
        )
        connection.commit()

    with (
        pytest.raises(RuntimeError, match="Multiple unmanaged administrators"),
        make_client(settings_for(database)),
    ):
        pass


def test_startup_disables_administrators_beside_the_configured_one(
    tmp_path: Path,
) -> None:
    """Only the configured account keeps administrator access.

    An extra administrator left over from an earlier installation is demoted
    and deactivated, and its refresh sessions revoked, so it cannot be used to
    regain access.
    """
    database = tmp_path / "extra-admin.db"
    with make_client(settings_for(database)):
        pass

    with database_connection(database) as connection:
        connection.execute(
            "DELETE FROM security_state WHERE key = 'managed_admin_user_id'"
        )
        connection.execute(
            "INSERT INTO users (username, display_name, password_hash,"
            " access_token_generation, is_admin, is_active, created_at)"
            " VALUES ('extra-admin', 'Extra', 'x', 0, true, true, now())"
        )
        connection.commit()
        extra_id = connection.execute(
            "SELECT id FROM users WHERE username = 'extra-admin'"
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO refresh_sessions (token_hash, user_id, expires_at,"
            " revoked_at, created_at)"
            " VALUES (%s, %s, %s, NULL, now())",
            ("a" * 64, extra_id, int(time()) + 3600),
        )
        connection.commit()

    with make_client(settings_for(database)):
        pass

    with database_connection(database) as connection:
        is_admin, is_active = connection.execute(
            "SELECT is_admin, is_active FROM users WHERE username = 'extra-admin'"
        ).fetchone()
        assert is_admin is False
        assert is_active is False
        revoked = connection.execute(
            "SELECT revoked_at FROM refresh_sessions WHERE user_id = %s",
            (extra_id,),
        ).fetchone()[0]
        assert revoked is not None
        # The configured administrator keeps its access.
        assert connection.execute(
            "SELECT is_admin AND is_active FROM users WHERE username = 'root-admin'"
        ).fetchone()[0]


def test_admin_deletes_a_professor_and_every_record_it_owns(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "delete-professor.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "departing.teacher",
                    "display_name": "Departing Teacher",
                    "password": "a-secure-departing-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client,
            "departing.teacher",
            "a-secure-departing-password",
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "Departing class", "grade_level": "6e"},
        ).json()
        account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={"first_name": "Departing", "last_name": "Pupil"},
        ).json()
        assert (
            client.post(
                f"/api/classes/{student_class['id']}/accounts/{account['id']}",
                headers=teacher_headers,
            ).status_code
            == 200
        )

        with client.app.state.session_factory() as session:
            teacher_id = session.scalar(
                select(User.id).where(User.username == "departing.teacher")
            )
            assert teacher_id is not None
            finished = seeded_exam_session(
                session,
                teacher_id,
                join_code="LEAVER1",
                status_value="finished",
                created_at=datetime.now(UTC),
                with_answer=True,
            )
            session.commit()

        users = client.get("/api/admin/users", headers=admin_headers).json()
        assert any(user["username"] == "departing.teacher" for user in users)

        deleted = client.delete(
            f"/api/admin/users/{teacher_id}",
            headers=admin_headers,
        )
        assert deleted.status_code == 204

        remaining = client.get("/api/admin/users", headers=admin_headers).json()
        assert all(user["username"] != "departing.teacher" for user in remaining)

        with client.app.state.session_factory() as session:
            assert session.get(User, teacher_id) is None
            assert session.get(QuizSession, finished) is None
            for model, column in (
                (StudentClass, StudentClass.owner_id),
                (StudentAccount, StudentAccount.owner_id),
                (QuestionBank, QuestionBank.owner_id),
                (Quiz, Quiz.owner_id),
            ):
                assert session.scalar(select(model).where(column == teacher_id)) is None
            assert (
                session.scalar(
                    select(Student).where(Student.class_id == student_class["id"])
                )
                is None
            )
            assert (
                session.scalar(
                    select(QuizAnswer).where(QuizAnswer.session_id == finished)
                )
                is None
            )
            assert (
                session.scalar(
                    select(QuizParticipant).where(
                        QuizParticipant.session_id == finished
                    )
                )
                is None
            )
            assert (
                session.scalar(
                    select(RefreshSession).where(RefreshSession.user_id == teacher_id)
                )
                is None
            )

        assert (
            client.delete(
                f"/api/admin/users/{teacher_id}",
                headers=admin_headers,
            ).status_code
            == 404
        )


def test_admin_cannot_delete_a_professor_running_an_exam(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "delete-busy-professor.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "busy.teacher",
                    "display_name": "Busy Teacher",
                    "password": "a-secure-busy-password",
                },
            ).status_code
            == 201
        )
        with client.app.state.session_factory() as session:
            teacher_id = session.scalar(
                select(User.id).where(User.username == "busy.teacher")
            )
            assert teacher_id is not None
            seeded_exam_session(
                session,
                teacher_id,
                join_code="RUNNING",
                status_value="in_progress",
                created_at=datetime.now(UTC),
                with_answer=True,
            )
            session.commit()

        refused = client.delete(
            f"/api/admin/users/{teacher_id}",
            headers=admin_headers,
        )

        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "TEACHER_IN_ACTIVE_EXAM"
        with client.app.state.session_factory() as session:
            assert session.get(User, teacher_id) is not None

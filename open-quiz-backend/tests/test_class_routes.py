"""Classes, student accounts, class imports and grade levels."""

from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select, text, update

from app.class_names import format_class_name
from app.models import (
    MakeupSession,
    StudentAccount,
)
from app.schemas import (
    StudentAccountUpdate,
)
from app.security import (
    encrypt_student_password,
)

from support import (
    complete_first_login,
    concurrent_writes,
    create_professor,
    exam_environment,
    launch_and_join,
    login_admin,
    make_client,
    settings_for,
)


def insert_account(identifier: str, owner_id: int):
    return lambda connection: connection.execute(
        StudentAccount.__table__.insert().values(
            owner_id=owner_id,
            identifier=identifier,
            display_name="Concurrent",
            password_hash="unused",
            access_token_generation=0,
            is_active=True,
        )
    )


def test_class_routes_reject_conflicts_and_unknown_records(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "class-edges")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        student_class = environment["student_class"]
        account = environment["account"]
        class_url = f"/api/classes/{student_class['id']}"

        missing = client.post(
            "/api/classes/999999/update",
            headers=headers,
            json={"name": "Missing", "grade_level": "5e"},
        )
        assert missing.status_code == 404
        assert missing.json()["detail"]["code"] == "CLASS_NOT_FOUND"

        filtered = client.get(
            "/api/classes",
            headers=headers,
            params={"search": "5e", "grade_level": "5e"},
        )
        assert [item["id"] for item in filtered.json()] == [student_class["id"]]
        assert (
            client.get(
                "/api/classes", headers=headers, params={"grade_level": "CM2"}
            ).json()
            == []
        )

        renamed = client.post(
            f"{class_url}/update",
            headers=headers,
            json={"name": "5e Alpha", "grade_level": "5e"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["name"] == "5e Alpha"

        same_class = client.post(
            f"{class_url}/accounts/{account['id']}", headers=headers
        )
        assert same_class.status_code == 200
        assert same_class.json()["student_count"] == 1

        unassigned = client.delete(f"{class_url}/accounts/999999", headers=headers)
        assert unassigned.status_code == 404
        assert unassigned.json()["detail"]["code"] == "CLASS_ASSIGNMENT_NOT_FOUND"

        other_class = client.post(
            "/api/classes", headers=headers, json={"name": "5e B", "grade_level": "5e"}
        ).json()
        launch_and_join(client, environment)
        transfer = client.post(
            f"/api/classes/{other_class['id']}/accounts/{account['id']}",
            headers=headers,
        )
        assert transfer.status_code == 409
        assert transfer.json()["detail"]["code"] == "STUDENT_TRANSFER_DURING_SESSION"
        unassign = client.delete(
            f"{class_url}/accounts/{account['id']}", headers=headers
        )
        assert unassign.status_code == 409
        assert unassign.json()["detail"]["code"] == "CLASS_HAS_ACTIVE_SESSION"
        busy_account = client.delete(f"/api/students/{account['id']}", headers=headers)
        assert busy_account.status_code == 409
        assert (
            busy_account.json()["detail"]["code"] == "STUDENT_ACCOUNT_IN_ACTIVE_SESSION"
        )


def test_a_class_with_an_active_makeup_session_cannot_be_deleted(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "class-makeup")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        student_class = environment["student_class"]
        with client.app.state.session_factory() as session:
            makeup = MakeupSession(
                owner_id=client.get("/api/users/me", headers=headers).json()["id"],
                class_id=student_class["id"],
                class_name=student_class["name"],
                join_code="MAKEUP01",
            )
            session.add(makeup)
            session.commit()
        refused = client.delete(f"/api/classes/{student_class['id']}", headers=headers)
        assert refused.status_code == 409
        assert refused.json()["detail"]["code"] == "CLASS_USED_BY_MAKEUP"
        assert "rattrapage" in refused.json()["detail"]["message"]


def test_class_writes_lose_concurrent_races_gracefully(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "class-races")) as client:
        admin_headers = login_admin(client)
        professor, headers = create_professor(client, admin_headers)
        assert (
            client.post(
                "/api/grade-levels", headers=headers, json={"name": "5e"}
            ).status_code
            == 201
        )

        with concurrent_writes(
            client,
            (
                "INSERT INTO student_accounts",
                insert_account("raced.pupil", professor["id"]),
            ),
        ) as fired:
            imported = client.post(
                "/api/classes/import",
                headers=headers,
                json={
                    "classes": [
                        {
                            "name": "Imported",
                            "grade_level": "5e",
                            "students": [
                                {"identifier": "raced.pupil", "display_name": "Pupil"}
                            ],
                        }
                    ]
                },
            )
        assert fired
        assert imported.status_code == 409

        student_class = client.post(
            "/api/classes", headers=headers, json={"name": "5e A", "grade_level": "5e"}
        ).json()
        account = client.post(
            "/api/students",
            headers=headers,
            json={"first_name": "Ada", "last_name": "Lovelace"},
        ).json()
        with concurrent_writes(
            client,
            (
                "INSERT INTO students",
                lambda connection: connection.execute(
                    text(
                        "INSERT INTO students (class_id, identifier, display_name, "
                        "created_at) VALUES (:class_id, :identifier, 'Legacy', now())"
                    ),
                    {
                        "class_id": student_class["id"],
                        "identifier": account["identifier"],
                    },
                ),
            ),
        ) as fired:
            assigned = client.post(
                f"/api/classes/{student_class['id']}/accounts/{account['id']}",
                headers=headers,
            )
        assert fired
        assert assigned.status_code == 409


def test_student_account_routes_cover_every_branch(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "student-edges")) as client:
        environment = exam_environment(client)
        headers = environment["teacher_headers"]
        assigned = environment["account"]

        def create(first_name: str, last_name: str) -> dict:
            response = client.post(
                "/api/students",
                headers=headers,
                json={"first_name": first_name, "last_name": last_name},
            )
            assert response.status_code == 201
            return response.json()

        first = create("Marie-Hélène", "Dubois-Martinez")
        second = create("Marie-Hélène", "Dubois-Martinez")
        third = create("Marie-Hélène", "Dubois-Martinez")
        assert first["identifier"] == "marie.helene.dubois"
        assert second["identifier"] == "marie.helene.duboi.2"
        assert third["identifier"] == "marie.helene.duboi.3"

        searched = client.get(
            "/api/students", headers=headers, params={"search": "duboi.3"}
        )
        assert [item["id"] for item in searched.json()] == [third["id"]]
        assert (
            client.get(
                "/api/students", headers=headers, params={"class_id": 999999}
            ).status_code
            == 404
        )

        renamed = client.post(
            f"/api/students/{assigned['id']}/update",
            headers=headers,
            json={"identifier": assigned["identifier"], "display_name": "Renamed"},
        )
        assert renamed.status_code == 200
        assert renamed.json()["display_name"] == "Renamed"

        conflict = client.post(
            f"/api/students/{second['id']}/update",
            headers=headers,
            json={"identifier": first["identifier"], "display_name": "Clash"},
        )
        assert conflict.status_code == 409

        with client.app.state.session_factory() as session:
            session.execute(
                update(StudentAccount)
                .where(StudentAccount.id == third["id"])
                .values(encrypted_password=None)
            )
            session.commit()
        credentials = client.get("/api/students/credentials", headers=headers)
        assert credentials.status_code == 200
        passwords = {
            item["identifier"]: item["password"] for item in credentials.json()
        }
        assert passwords[third["identifier"]] is None
        assert passwords[first["identifier"]]

        assert (
            client.delete(f"/api/students/{third['id']}", headers=headers).status_code
            == 204
        )

        owner_id = client.get("/api/users/me", headers=headers).json()["id"]
        with concurrent_writes(
            client,
            ("INSERT INTO student_accounts", insert_account("ada.lovelace", owner_id)),
        ) as fired:
            raced = client.post(
                "/api/students",
                headers=headers,
                json={"first_name": "Ada", "last_name": "Lovelace"},
            )
        assert fired
        assert raced.status_code == 409


@pytest.mark.parametrize("password", ["shortpass", "abcdeabcde"])
def test_student_password_resets_reject_weak_values(password: str) -> None:
    with pytest.raises(ValidationError):
        StudentAccountUpdate.model_validate(
            {
                "identifier": "student.account",
                "display_name": "Student Account",
                "password": password,
            }
        )


def test_professor_manages_student_accounts_and_class_assignments(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "student-accounts.db")) as client:
        admin_headers = login_admin(client)
        created_teacher = client.post(
            "/api/admin/users",
            headers=admin_headers,
            json={
                "username": "account.teacher",
                "display_name": "Account Teacher",
                "password": "a-secure-teacher-password",
            },
        )
        assert created_teacher.status_code == 201
        teacher_headers, _ = complete_first_login(
            client,
            "account.teacher",
            "a-secure-teacher-password",
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "4e A", "grade_level": "4e"},
        ).json()

        created = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Léa",
                "last_name": "Dupont",
            },
        )
        assert created.status_code == 201
        account = created.json()
        assert account["class_id"] is None
        assert "password" not in account
        assert account["identifier"] == "lea.dupont"
        generated_password = account["generated_password"]
        assert len(generated_password) == 10
        assert generated_password[:8].isalpha()
        assert generated_password[:8].isupper()
        assert generated_password[8:].isdigit()
        credentials_response = client.get(
            "/api/students/credentials", headers=teacher_headers
        )
        assert credentials_response.status_code == 200
        assert credentials_response.headers["cache-control"] == "no-store"
        assert credentials_response.json() == [
            {
                "identifier": "lea.dupont",
                "display_name": "Léa Dupont",
                "password": generated_password,
            }
        ]
        exported = client.get(
            "/api/students/credentials/export", headers=teacher_headers
        )
        assert exported.status_code == 200
        assert exported.headers["cache-control"] == "no-store"
        assert exported.headers["content-disposition"] == (
            'attachment; filename="student-credentials.json"'
        )
        assert exported.json() == {"students": credentials_response.json()}
        assert client.get("/api/students/credentials").status_code == 401
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "other.account.teacher",
                    "display_name": "Other Account Teacher",
                    "password": "another-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        other_teacher_headers, _ = complete_first_login(
            client,
            "other.account.teacher",
            "another-secure-teacher-password",
        )
        assert (
            client.get(
                "/api/students/credentials", headers=other_teacher_headers
            ).json()
            == []
        )
        with client.app.state.session_factory() as session:
            stored_account = session.scalar(
                select(StudentAccount).where(StudentAccount.id == account["id"])
            )
            assert stored_account is not None
            assert stored_account.encrypted_password
            assert generated_password not in stored_account.encrypted_password
        inactive_account = client.post(
            "/api/students",
            headers=teacher_headers,
            json={
                "first_name": "Inactive",
                "last_name": "Student",
            },
        ).json()
        assert (
            client.post(
                f"/api/students/{inactive_account['id']}/update",
                headers=teacher_headers,
                json={
                    "identifier": inactive_account["identifier"],
                    "display_name": inactive_account["display_name"],
                    "is_active": False,
                },
            ).status_code
            == 200
        )

        logged_in = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "LEA.DUPONT",
                "password": account["generated_password"],
            },
        )
        assert logged_in.status_code == 200
        invalid_student_login = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "lea.dupont",
                "password": "incorrect-password",
            },
        )
        assert invalid_student_login.status_code == 401
        assert (
            invalid_student_login.json()["detail"]["code"] == "AUTH_INVALID_CREDENTIALS"
        )
        student_headers = {
            "Authorization": f"Bearer {logged_in.json()['access_token']}"
        }
        assert (
            client.get("/api/student-auth/me", headers=student_headers).json()[
                "display_name"
            ]
            == "Léa Dupont"
        )

        assigned = client.post(
            f"/api/classes/{student_class['id']}/accounts/{account['id']}",
            headers=teacher_headers,
        )
        assert assigned.status_code == 200
        assert assigned.json()["students"][0]["account_id"] == account["id"]
        class_credentials = client.get(
            "/api/students/credentials",
            headers=teacher_headers,
            params={"class_id": student_class["id"]},
        )
        assert class_credentials.status_code == 200
        assert [item["identifier"] for item in class_credentials.json()] == [
            account["identifier"]
        ]
        assert (
            client.get(
                "/api/students/credentials",
                headers=other_teacher_headers,
                params={"class_id": student_class["id"]},
            ).status_code
            == 404
        )
        listed_accounts = client.get("/api/students", headers=teacher_headers).json()
        assert all("password" not in item for item in listed_accounts)
        assert (
            next(item for item in listed_accounts if item["id"] == account["id"])[
                "class_name"
            ]
            == "4e A"
        )
        assert [
            item["id"]
            for item in client.get(
                "/api/students",
                headers=teacher_headers,
                params={"class_id": student_class["id"]},
            ).json()
        ] == [account["id"]]
        assert [
            item["id"]
            for item in client.get(
                "/api/students",
                headers=teacher_headers,
                params={"unassigned": True},
            ).json()
        ] == [inactive_account["id"]]
        assert [
            item["id"]
            for item in client.get(
                "/api/students",
                headers=teacher_headers,
                params={"is_active": False},
            ).json()
        ] == [inactive_account["id"]]
        assert (
            client.get(
                "/api/students",
                headers=teacher_headers,
                params={"class_id": student_class["id"], "unassigned": True},
            ).status_code
            == 422
        )

        unassigned = client.delete(
            f"/api/classes/{student_class['id']}/accounts/{account['id']}",
            headers=teacher_headers,
        )
        assert unassigned.status_code == 204
        listed_accounts = client.get("/api/students", headers=teacher_headers).json()
        assert (
            next(item for item in listed_accounts if item["id"] == account["id"])[
                "class_id"
            ]
            is None
        )


def test_unreadable_student_password_is_reported_as_unavailable(
    tmp_path: Path,
) -> None:
    """A rotated credential key must not fail the whole listing and export."""
    with make_client(settings_for(tmp_path / "stale-credentials.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "stale.credentials.teacher",
                    "display_name": "Stale Credentials Teacher",
                    "password": "a-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client,
            "stale.credentials.teacher",
            "a-secure-teacher-password",
        )
        readable = client.post(
            "/api/students",
            headers=teacher_headers,
            json={"first_name": "Lisa", "last_name": "Martin"},
        ).json()
        stale = client.post(
            "/api/students",
            headers=teacher_headers,
            json={"first_name": "Noé", "last_name": "Bernard"},
        ).json()

        # Simulate a password stored under a previous encryption key.
        with client.app.state.session_factory() as session:
            account = session.get(StudentAccount, stale["id"])
            assert account is not None
            account.encrypted_password = encrypt_student_password(
                "a-previous-password",
                "a-rotated-student-credential-key-2026",
            )
            session.commit()

        credentials = client.get("/api/students/credentials", headers=teacher_headers)
        assert credentials.status_code == 200
        passwords_by_identifier = {
            item["identifier"]: item["password"] for item in credentials.json()
        }
        assert (
            passwords_by_identifier[readable["identifier"]]
            == readable["generated_password"]
        )
        assert passwords_by_identifier[stale["identifier"]] is None

        exported = client.get(
            "/api/students/credentials/export", headers=teacher_headers
        )
        assert exported.status_code == 200
        assert exported.json() == {"students": credentials.json()}


def test_class_import_creates_accounts_and_rejects_conflicts(tmp_path: Path) -> None:
    """The bulk class importer is the only way to choose student identifiers."""
    with make_client(settings_for(tmp_path / "class-import.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "import.teacher",
                    "display_name": "Import Teacher",
                    "password": "a-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client, "import.teacher", "a-secure-teacher-password"
        )
        levels = client.get("/api/grade-levels", headers=teacher_headers).json()
        level = levels[0]["name"]

        example = client.get("/api/classes/example", headers=teacher_headers)
        assert example.status_code == 200
        assert example.headers["content-disposition"].endswith(
            'filename="open-quiz-classes-example.json"'
        )

        def import_payload(classes: list[dict[str, Any]]) -> dict[str, Any]:
            return {"classes": classes}

        duplicate_classes = client.post(
            "/api/classes/import",
            headers=teacher_headers,
            json=import_payload(
                [
                    {"name": "TG1", "grade_level": level, "students": []},
                    {"name": "tg1", "grade_level": level, "students": []},
                ]
            ),
        )
        assert duplicate_classes.status_code == 422
        assert duplicate_classes.json()["detail"]["code"] == "CLASS_IMPORT_DUPLICATES"

        duplicate_identifiers = client.post(
            "/api/classes/import",
            headers=teacher_headers,
            json=import_payload(
                [
                    {
                        "name": "TG1",
                        "grade_level": level,
                        "students": [
                            {"identifier": "a.martin", "display_name": "A Martin"},
                            {"identifier": "a.martin", "display_name": "Autre Martin"},
                        ],
                    }
                ]
            ),
        )
        assert duplicate_identifiers.status_code == 422
        assert (
            duplicate_identifiers.json()["detail"]["code"] == "CLASS_IMPORT_DUPLICATES"
        )

        unknown_level = client.post(
            "/api/classes/import",
            headers=teacher_headers,
            json=import_payload(
                [{"name": "TG1", "grade_level": "Niveau inconnu", "students": []}]
            ),
        )
        assert unknown_level.status_code == 422
        assert (
            unknown_level.json()["detail"]["code"] == "CLASS_IMPORT_GRADE_LEVEL_INVALID"
        )
        assert "Niveau inconnu" in unknown_level.json()["detail"]["message"]

        imported = client.post(
            "/api/classes/import",
            headers=teacher_headers,
            json=import_payload(
                [
                    {
                        "name": "TG1",
                        "grade_level": level,
                        "students": [
                            {"identifier": "a.martin", "display_name": "Alice Martin"},
                            {"identifier": "b.dupont", "display_name": "Bruno Dupont"},
                        ],
                    }
                ]
            ),
        )
        assert imported.status_code == 201
        assert imported.json() == {"class_count": 1, "student_count": 2}

        credentials = client.get(
            "/api/students/credentials", headers=teacher_headers
        ).json()
        by_identifier = {item["identifier"]: item for item in credentials}
        assert set(by_identifier) == {"a.martin", "b.dupont"}
        # The importer must generate a usable password for every account.
        logged_in = client.post(
            "/api/student-auth/login",
            json={
                "identifier": "a.martin",
                "password": by_identifier["a.martin"]["password"],
            },
        )
        assert logged_in.status_code == 200

        existing_class = client.post(
            "/api/classes/import",
            headers=teacher_headers,
            json=import_payload(
                [{"name": "TG1", "grade_level": level, "students": []}]
            ),
        )
        assert existing_class.status_code == 409

        # Identifiers are globally unique, so another teacher cannot claim one.
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "other.import.teacher",
                    "display_name": "Other Import Teacher",
                    "password": "another-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        other_headers, _ = complete_first_login(
            client, "other.import.teacher", "another-secure-teacher-password"
        )
        other_level = client.get("/api/grade-levels", headers=other_headers).json()[0]
        taken_identifier = client.post(
            "/api/classes/import",
            headers=other_headers,
            json=import_payload(
                [
                    {
                        "name": "TG2",
                        "grade_level": other_level["name"],
                        "students": [
                            {"identifier": "a.martin", "display_name": "Homonyme"}
                        ],
                    }
                ]
            ),
        )
        assert taken_identifier.status_code == 409
        # The rejected import must not have created a partial class.
        assert client.get("/api/classes", headers=other_headers).json() == []


def test_grade_level_deletion_is_blocked_while_in_use(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "grade-level-in-use.db")) as client:
        admin_headers = login_admin(client)
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "level.teacher",
                    "display_name": "Level Teacher",
                    "password": "a-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        teacher_headers, _ = complete_first_login(
            client, "level.teacher", "a-secure-teacher-password"
        )
        level = client.post(
            "/api/grade-levels",
            headers=teacher_headers,
            json={"name": "Niveau supprimable"},
        ).json()

        bank = client.post(
            "/api/question-banks",
            headers=teacher_headers,
            json={"grade_level": level["name"], "chapter": "Chapitre"},
        )
        assert bank.status_code == 201
        blocked_by_bank = client.delete(
            f"/api/grade-levels/{level['id']}", headers=teacher_headers
        )
        assert blocked_by_bank.status_code == 409

        assert (
            client.delete(
                f"/api/question-banks/{bank.json()['id']}", headers=teacher_headers
            ).status_code
            == 204
        )
        student_class = client.post(
            "/api/classes",
            headers=teacher_headers,
            json={"name": "Classe", "grade_level": level["name"]},
        )
        assert student_class.status_code == 201
        blocked_by_class = client.delete(
            f"/api/grade-levels/{level['id']}", headers=teacher_headers
        )
        assert blocked_by_class.status_code == 409

        # While the level still exists, another teacher must not reach it: a
        # 404 here has to come from ownership scoping, not from a missing row.
        assert (
            client.post(
                "/api/admin/users",
                headers=admin_headers,
                json={
                    "username": "other.level.teacher",
                    "display_name": "Other Level Teacher",
                    "password": "another-secure-teacher-password",
                },
            ).status_code
            == 201
        )
        other_headers, _ = complete_first_login(
            client, "other.level.teacher", "another-secure-teacher-password"
        )
        assert (
            client.delete(
                f"/api/grade-levels/{level['id']}", headers=other_headers
            ).status_code
            == 404
        )

        assert (
            client.delete(
                f"/api/classes/{student_class.json()['id']}", headers=teacher_headers
            ).status_code
            == 204
        )
        assert (
            client.delete(
                f"/api/grade-levels/{level['id']}", headers=teacher_headers
            ).status_code
            == 204
        )


@pytest.mark.parametrize(
    ("grade_level", "class_name", "expected"),
    [
        # The level is prepended when the name does not already carry it.
        ("Tle", "TG1", "Tle TG1"),
        ("Tle", "Tle TG1", "Tle TG1"),
        # A name equal to the level stays as written.
        ("Tle", "Tle", "Tle"),
        ("Tle", "tle", "tle"),
        # Either side missing leaves the other untouched.
        (None, "TG1", "TG1"),
        ("", "TG1", "TG1"),
        ("Tle", "", "Tle"),
        # A level repeated around a separator is folded back into the prefix,
        # for each separator teachers actually type.
        ("Tle", "TG1 - Tle", "Tle TG1"),
        ("Tle", "TG1 — Tle", "Tle TG1"),
        ("Tle", "TG1 · Tle", "Tle TG1"),
        ("Tle", "Tle - TG1", "Tle TG1"),
        ("Tle", "Tle — TG1", "Tle TG1"),
        ("Tle", "Tle · TG1", "Tle TG1"),
        # Matching ignores case on both sides.
        ("Tle", "tle - TG1", "Tle TG1"),
        ("Tle", "TG1 - TLE", "Tle TG1"),
        # Surrounding and repeated whitespace is collapsed.
        ("Tle", "  TG1   B  ", "Tle TG1 B"),
        ("  Tle  ", "TG1", "Tle TG1"),
        # A level that merely starts the name is not a separator match.
        ("1ere", "1ere-A", "1ere 1ere-A"),
    ],
)
def test_class_labels_are_built_without_repeating_the_level(
    grade_level: str | None, class_name: str, expected: str
) -> None:
    """This label is stored in session snapshots and printed in CSV exports.

    The interface builds the same label with formatClassName in
    open-quiz-frontend/src/lib/utils.ts; the two must agree, so keep this
    table and that function in step.
    """
    assert format_class_name(grade_level, class_name) == expected

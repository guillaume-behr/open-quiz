"""Class and student account paths outside the main flows."""

from pathlib import Path

from sqlalchemy import text, update

from app.models import MakeupSession, StudentAccount

from support import (
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

        assert (
            client.post(
                "/api/classes/999999/update",
                headers=headers,
                json={"name": "Missing", "grade_level": "5e"},
            ).status_code
            == 404
        )

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

        assert (
            client.delete(f"{class_url}/accounts/999999", headers=headers).status_code
            == 404
        )

        other_class = client.post(
            "/api/classes", headers=headers, json={"name": "5e B", "grade_level": "5e"}
        ).json()
        launch_and_join(client, environment)
        transfer = client.post(
            f"/api/classes/{other_class['id']}/accounts/{account['id']}",
            headers=headers,
        )
        assert transfer.status_code == 409
        unassign = client.delete(
            f"{class_url}/accounts/{account['id']}", headers=headers
        )
        assert unassign.status_code == 409
        busy_account = client.delete(f"/api/students/{account['id']}", headers=headers)
        assert busy_account.status_code == 409


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
        assert "rattrapage" in refused.json()["detail"]


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

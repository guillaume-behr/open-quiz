"""Grade levels, class names and bank names are unique per teacher, ignoring case."""

from pathlib import Path
from typing import Any

from sqlalchemy import text

from support import (
    concurrent_writes,
    create_professor,
    login_admin,
    make_client,
    settings_for,
)


def level_names(client: Any, headers: dict[str, str]) -> list[str]:
    return [
        level["name"]
        for level in client.get("/api/classes/grade-levels", headers=headers).json()
    ]


def test_a_level_differing_only_by_case_reuses_the_existing_one(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "level-case")) as client:
        _, headers = create_professor(client, login_admin(client))
        assert "Tle" in level_names(client, headers)

        created = client.post(
            "/api/classes", headers=headers, json={"name": "T1", "grade_level": "tle"}
        )
        assert created.status_code == 201
        assert created.json()["grade_level"] == "Tle"
        bank = client.post(
            "/api/question-banks",
            headers=headers,
            json={"grade_level": "TLE", "chapter": "Suites"},
        )
        assert bank.status_code == 201
        assert bank.json()["grade_level"] == "Tle"
        imported = client.post(
            "/api/question-banks/import",
            headers=headers,
            json={
                "version": 1,
                "question_bank": {"grade_level": "tLe", "chapter": "Limites"},
                "questions": [],
            },
        )
        assert imported.status_code == 201
        classes = client.post(
            "/api/classes/import",
            headers=headers,
            json={"classes": [{"name": "T2", "grade_level": "tle", "students": []}]},
        )
        assert classes.status_code == 201
        assert level_names(client, headers).count("Tle") == 1
        assert [
            level for level in level_names(client, headers) if level.lower() == "tle"
        ] == ["Tle"]
        listed = client.get("/api/classes", headers=headers).json()["items"]
        assert {item["grade_level"] for item in listed} == {"Tle"}


def test_names_differing_only_by_case_are_taken(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "name-case")) as client:
        _, headers = create_professor(client, login_admin(client))
        assert (
            client.post(
                "/api/classes",
                headers=headers,
                json={"name": "TG1", "grade_level": "Tle"},
            ).status_code
            == 201
        )
        clash = client.post(
            "/api/classes", headers=headers, json={"name": "tg1", "grade_level": "Tle"}
        )
        assert clash.status_code == 409
        assert clash.json()["code"] == "CLASS_NAME_TAKEN"
        other = client.post(
            "/api/classes", headers=headers, json={"name": "TG2", "grade_level": "Tle"}
        ).json()
        renamed = client.post(
            f"/api/classes/{other['id']}/update",
            headers=headers,
            json={"name": "Tg1", "grade_level": "Tle"},
        )
        assert renamed.status_code == 409
        assert renamed.json()["code"] == "CLASS_NAME_TAKEN"
        imported = client.post(
            "/api/classes/import",
            headers=headers,
            json={"classes": [{"name": "tG1", "grade_level": "Tle", "students": []}]},
        )
        assert imported.status_code == 409
        assert imported.json()["code"] == "CLASS_NAME_TAKEN"
        # Python's casefold() folds "ß" to "ss", PostgreSQL's lower() does not:
        # the import compares the way the database does.
        assert (
            client.post(
                "/api/classes",
                headers=headers,
                json={"name": "Groß", "grade_level": "Tle"},
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/api/classes/import",
                headers=headers,
                json={
                    "classes": [{"name": "GROSS", "grade_level": "Tle", "students": []}]
                },
            ).status_code
            == 201
        )

        for grade_level, chapter in (("Tle", "Suites"), ("tle", "SUITES")):
            created = client.post(
                "/api/question-banks",
                headers=headers,
                json={"grade_level": grade_level, "chapter": chapter},
            )
        assert created.status_code == 409
        assert created.json()["code"] == "QUESTION_BANK_NAME_TAKEN"
        imported_bank = client.post(
            "/api/question-banks/import",
            headers=headers,
            json={
                "version": 1,
                "question_bank": {"grade_level": "TLE", "chapter": "suites"},
                "questions": [],
            },
        )
        assert imported_bank.status_code == 409
        assert imported_bank.json()["code"] == "QUESTION_BANK_NAME_TAKEN"


def test_a_concurrent_level_insert_is_not_a_name_clash(tmp_path: Path) -> None:
    """Another request creating the same level first does not fail this one."""
    with make_client(settings_for(tmp_path / "level-race")) as client:
        professor, headers = create_professor(client, login_admin(client))

        def insert_level(name: str):
            def insert(connection: Any) -> None:
                connection.execute(
                    text(
                        "INSERT INTO grade_levels (owner_id, name, created_at) "
                        "VALUES (:owner_id, :name, now())"
                    ),
                    {"owner_id": professor["id"], "name": name},
                )

            return insert

        with concurrent_writes(
            client, ("INSERT INTO grade_levels", insert_level("CM1"))
        ) as fired:
            created = client.post(
                "/api/classes",
                headers=headers,
                json={"name": "CM1 A", "grade_level": "cm1"},
            )
        assert fired
        assert created.status_code == 201
        assert created.json()["grade_level"] == "CM1"

        with concurrent_writes(
            client, ("INSERT INTO grade_levels", insert_level("CM2"))
        ) as fired:
            bank = client.post(
                "/api/question-banks",
                headers=headers,
                json={"grade_level": "CM2", "chapter": "Fractions"},
            )
        assert fired
        assert bank.status_code == 201
        assert level_names(client, headers).count("CM2") == 1

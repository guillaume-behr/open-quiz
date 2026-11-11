"""Sign-in hardening: guess budget, session cap, hash upgrade, pool use."""

from pathlib import Path
from typing import Any

import pytest
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import event, select, update

from app import security
from app.models import StudentAccount, User
from app.routers import auth, student_auth
from app.routers.auth import REFRESH_COOKIE

from support import (
    ADMIN_PASSWORD,
    complete_first_login,
    exam_environment,
    make_client,
    refresh_headers,
    settings_for,
)

WEAK_HASHER = PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8, parallelism=1),))


def student_login(client: Any, account: dict[str, Any], password: str | None = None):
    return client.post(
        "/api/student-auth/login",
        json={
            "identifier": account["identifier"],
            "password": password or account["generated_password"],
        },
    )


def test_a_successful_login_does_not_refill_an_attackers_guesses(
    tmp_path: Path,
) -> None:
    with make_client(settings_for(tmp_path / "guesses", login_attempts=3)) as client:
        account = exam_environment(client)["account"]
        for _ in range(2):
            assert student_login(client, account, "wrong-guess").status_code == 401
        # The owner signs in: only their own attempt is given back.
        assert student_login(client, account).status_code == 200
        assert student_login(client, account, "wrong-guess").status_code == 401
        assert student_login(client, account, "wrong-guess").status_code == 429


def test_a_session_evicted_by_the_cap_is_not_reported_as_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with make_client(settings_for(tmp_path / "cap")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        oldest = client.cookies.get(REFRESH_COOKIE)
        for _ in range(10):
            # The browser is trusted, so the password alone opens a session.
            assert (
                client.post(
                    "/api/auth/login",
                    json={"username": "root-admin", "password": ADMIN_PASSWORD},
                ).status_code
                == 200
            )
        newest = client.cookies.get(REFRESH_COOKIE)
        events: list[str] = []
        monkeypatch.setattr(auth, "audit_event", lambda name, **_: events.append(name))

        client.cookies.clear()
        client.cookies.set(REFRESH_COOKIE, oldest, path="/api/auth")
        evicted = client.post("/api/auth/refresh", headers=refresh_headers(client))
        assert evicted.status_code == 401
        assert "auth.refresh_reuse_detected" not in events

        # The other sessions were left alone.
        client.cookies.clear()
        client.cookies.set(REFRESH_COOKIE, newest, path="/api/auth")
        assert (
            client.post("/api/auth/refresh", headers=refresh_headers(client))
        ).status_code == 200


def test_an_outdated_password_hash_is_upgraded_at_login(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "rehash")) as client:
        account = exam_environment(client)["account"]
        earlier = student_login(client, account).json()["access_token"]
        weak_hash = WEAK_HASHER.hash(account["generated_password"])
        with client.app.state.session_factory() as session:
            session.execute(
                update(StudentAccount)
                .where(StudentAccount.id == account["id"])
                .values(password_hash=weak_hash)
            )
            session.commit()

        signed_in = student_login(client, account)

        assert signed_in.status_code == 200
        with client.app.state.session_factory() as session:
            stored = session.get(StudentAccount, account["id"])
            assert stored is not None
            assert stored.password_hash != weak_hash
            assert not security.password_hash.current_hasher.check_needs_rehash(
                stored.password_hash
            )
        # The new token works. Tokens are bound to the hash, so the ones
        # issued before the upgrade are signed out, as after a password change.
        new_headers = {"Authorization": f"Bearer {signed_in.json()['access_token']}"}
        old_headers = {"Authorization": f"Bearer {earlier}"}
        assert (
            client.get("/api/student-auth/me", headers=new_headers).status_code == 200
        )
        assert (
            client.get("/api/student-auth/me", headers=old_headers).status_code == 401
        )


@pytest.mark.parametrize("module", [auth, student_auth])
def test_no_connection_is_held_while_waiting_for_the_password_hash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, module: Any
) -> None:
    with make_client(settings_for(tmp_path / "pool")) as client:
        environment = exam_environment(client)
        engine = client.app.state.session_factory.kw["bind"]
        held: list[int] = []
        verify = module.verify_password_and_update

        def watched(password: str, encoded: str):
            held.append(engine.pool.checkedout())
            return verify(password, encoded)

        monkeypatch.setattr(module, "verify_password_and_update", watched)
        if module is auth:
            client.post(
                "/api/auth/login",
                json={"username": "edge.teacher", "password": "a-secure-edge-password"},
            )
        else:
            student_login(client, environment["account"])
        assert held == [0]


def test_signing_in_does_not_sweep_expired_sessions(tmp_path: Path) -> None:
    """The hourly maintenance does that; every login used to repeat it."""
    with make_client(settings_for(tmp_path / "sweep")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        engine = client.app.state.session_factory.kw["bind"]
        deletes: list[str] = []

        def record(_connection, _cursor, statement, *_args) -> None:
            if statement.lstrip().upper().startswith("DELETE FROM REFRESH_SESSION"):
                deletes.append(statement)

        event.listen(engine, "before_cursor_execute", record)
        try:
            assert (
                client.post("/api/auth/refresh", headers=refresh_headers(client))
            ).status_code == 200
        finally:
            event.remove(engine, "before_cursor_execute", record)
        assert deletes == []


def test_a_teachers_outdated_password_hash_is_upgraded_too(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "rehash-teacher")) as client:
        complete_first_login(client, "root-admin", ADMIN_PASSWORD)
        weak_hash = WEAK_HASHER.hash(ADMIN_PASSWORD)
        with client.app.state.session_factory() as session:
            session.execute(
                update(User)
                .where(User.username == "root-admin")
                .values(password_hash=weak_hash)
            )
            session.commit()

        # The browser is trusted, so the password alone signs in.
        signed_in = client.post(
            "/api/auth/login",
            json={"username": "root-admin", "password": ADMIN_PASSWORD},
        )

        assert signed_in.status_code == 200
        with client.app.state.session_factory() as session:
            stored = session.scalars(
                select(User.password_hash).where(User.username == "root-admin")
            ).one()
        assert stored != weak_hash
        assert not security.password_hash.current_hasher.check_needs_rehash(stored)

"""Boundary and malformed-input cases for scoring, tokens, TOTP and limiters.

These pin behaviour the route tests only reach on the happy path: what a
limiter does exactly at its limit, which TOTP counters a code may match, how a
score rounds, and how pagination answers out-of-range pages.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import jwt
import pyotp
import pytest
from cryptography.fernet import InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app import rate_limit, security
from app.database import build_session_factory
from app.models import (
    LoginRateLimit,
    Question,
    QuestionBank,
    QuestionChoice,
    User,
)
from app.pagination import MAX_PAGE, MAX_PAGE_SIZE, contains_pattern
from app.rate_limit import FixedWindowRateLimiter, LoginRateLimiter
from app.security import (
    TWO_FACTOR_TRUST_MAXIMUM,
    create_access_token,
    create_student_access_token,
    create_two_factor_token,
    decode_access_token,
    decode_student_access_token,
    decode_two_factor_token,
    decrypt_student_password,
    decrypt_totp_secret,
    encrypt_student_password,
    encrypt_totp_secret,
    end_of_trusted_day,
    hash_password,
    hash_refresh_token,
    refresh_request_proof,
    verify_totp_code,
)
from app.services.grading import (
    question_maximum_scores,
    selected_choice_ids,
    selected_choice_score,
)

from support import (
    JWT_SECRET,
    create_professor,
    login_admin,
    make_client,
    settings_for,
)

OTHER_SECRET = "another-secret-that-is-long-enough-too"


# --- Scoring -----------------------------------------------------------------


def choice(choice_id: int, *, correct: bool, points: float) -> QuestionChoice:
    return QuestionChoice(id=choice_id, is_correct=correct, points=points)


@pytest.mark.parametrize("allow_negative_points", [False, True])
def test_an_empty_selection_scores_zero(allow_negative_points: bool) -> None:
    choices = [choice(1, correct=True, points=1), choice(2, correct=False, points=-1)]
    assert (
        selected_choice_score(
            choices, set(), allow_negative_points=allow_negative_points
        )
        == 0
    )


def test_a_question_without_choices_scores_zero() -> None:
    assert selected_choice_score([], {1, 2}, allow_negative_points=True) == 0


def test_selected_ids_from_another_question_are_ignored() -> None:
    # A forged payload can name any id: only this question's choices count.
    choices = [choice(1, correct=True, points=2)]
    assert selected_choice_score(choices, {1, 999}, allow_negative_points=False) == 2


def test_scores_are_rounded_to_two_decimals() -> None:
    choices = [
        choice(1, correct=True, points=0.1),
        choice(2, correct=True, points=0.2),
        choice(3, correct=True, points=1 / 3),
    ]
    assert selected_choice_score(choices, {1, 2}, allow_negative_points=False) == 0.3
    assert (
        selected_choice_score(choices, {1, 2, 3}, allow_negative_points=False) == 0.63
    )


def test_a_negative_correct_choice_only_costs_in_negative_mode() -> None:
    choices = [
        choice(1, correct=True, points=2),
        choice(2, correct=True, points=-0.5),
    ]
    assert selected_choice_score(choices, {1, 2}, allow_negative_points=False) == 2
    assert selected_choice_score(choices, {1, 2}, allow_negative_points=True) == 1.5


def test_a_priced_distractor_alone_scores_below_zero_in_negative_mode() -> None:
    choices = [
        choice(1, correct=True, points=1),
        choice(2, correct=False, points=-0.5),
    ]
    assert selected_choice_score(choices, {2}, allow_negative_points=True) == -0.5
    assert selected_choice_score(choices, {2}, allow_negative_points=False) == 0


def test_a_positive_distractor_still_zeroes_the_question_in_negative_mode() -> None:
    choices = [
        choice(1, correct=True, points=1),
        choice(2, correct=False, points=0.5),
        choice(3, correct=False, points=-0.25),
    ]
    assert selected_choice_score(choices, {1, 2, 3}, allow_negative_points=True) == 0


def stored_answer(answer_data: str) -> SimpleNamespace:
    return SimpleNamespace(answer_data=answer_data)


@pytest.mark.parametrize(
    ("answer_data", "expected"),
    [
        ("{}", set()),
        ('{"selected_choice_ids": null}', set()),
        ('{"selected_choice_ids": "12"}', set()),
        ('{"selected_choice_ids": 12}', set()),
        ('{"selected_choice_ids": {"1": true}}', set()),
        ('{"selected_choice_ids": []}', set()),
        ('{"selected_choice_ids": [1, 1, 2]}', {1, 2}),
        ('{"text": "free text"}', set()),
    ],
)
def test_selected_choice_ids_tolerate_odd_payloads(
    answer_data: str, expected: set[int]
) -> None:
    assert selected_choice_ids(stored_answer(answer_data)) == expected


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        # Unhashable entries used to make set() raise a TypeError.
        ("[[1]]", set()),
        ('[{"id": 1}]', set()),
        ('[1, [2], {"id": 3}, 4]', {1, 4}),
        # Booleans compare equal to ids 0 and 1, and strings never match an id.
        ("[true, false]", set()),
        ('["1", 1.5, null]', set()),
    ],
)
def test_selected_choice_ids_keep_only_integer_ids(
    entries: str, expected: set[int]
) -> None:
    assert (
        selected_choice_ids(stored_answer(f'{{"selected_choice_ids": {entries}}}'))
        == expected
    )


def test_a_corrupted_selection_scores_zero_instead_of_crashing() -> None:
    choices = [choice(1, correct=True, points=1)]
    answer = stored_answer('{"selected_choice_ids": [[1], true]}')
    assert (
        selected_choice_score(
            choices, selected_choice_ids(answer), allow_negative_points=False
        )
        == 0
    )


# --- Question maximums (database) --------------------------------------------


@pytest.fixture
def session_factory(tmp_path: Path) -> sessionmaker[Session]:
    return build_session_factory(settings_for(tmp_path / "edges").database_url)


def add_question(
    session: Session, bank_id: int, answer_mode: str, choices: list[tuple[bool, float]]
) -> int:
    question = Question(
        question_bank_id=bank_id,
        prompt="Prompt",
        difficulty="easy",
        answer_mode=answer_mode,
        correction_mode="automatic",
    )
    session.add(question)
    session.flush()
    session.add_all(
        QuestionChoice(
            question_id=question.id,
            label=f"Choice {position}",
            is_correct=is_correct,
            points=points,
            position=position,
        )
        for position, (is_correct, points) in enumerate(choices)
    )
    session.flush()
    return question.id


def test_question_maximums_follow_the_scoring_rule(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        owner = User(
            username="owner",
            display_name="Owner",
            password_hash=hash_password("an-unused-password-value"),
        )
        session.add(owner)
        session.flush()
        bank = QuestionBank(owner_id=owner.id, grade_level="Tle", chapter="Edges")
        session.add(bank)
        session.flush()
        single = add_question(
            session, bank.id, "single", [(True, 1), (True, 3), (False, 5)]
        )
        multiple = add_question(
            session,
            bank.id,
            "multiple",
            [(True, 1.25), (True, 2), (True, -1), (False, 4)],
        )
        written = add_question(session, bank.id, "written", [])
        only_distractors = add_question(
            session, bank.id, "multiple", [(False, 2), (False, -1)]
        )
        unknown = 10**9

        maximums = question_maximum_scores(
            [single, multiple, written, only_distractors, unknown], session
        )

    # A single-answer question pays its best correct choice, never their sum.
    assert maximums[single] == 3
    # Negative correct choices and priced distractors never raise the ceiling.
    assert maximums[multiple] == 3.25
    assert maximums[written] == 0
    assert maximums[only_distractors] == 0
    assert maximums[unknown] == 0
    assert list(maximums) == [single, multiple, written, only_distractors, unknown]


# --- Tokens ------------------------------------------------------------------


def unsigned_token(payload: dict) -> str:
    return jwt.encode(payload, key=None, algorithm="none")


def claims(token_type: str, **extra) -> dict:
    now = datetime.now(UTC)
    return {
        "sub": "1",
        "type": token_type,
        "ver": "version",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        **extra,
    }


@pytest.mark.parametrize("decode", [decode_access_token, decode_student_access_token])
def test_unsigned_tokens_are_refused(decode) -> None:
    for token_type in ("access", "student_access"):
        with pytest.raises(jwt.InvalidTokenError):
            decode(unsigned_token(claims(token_type)), JWT_SECRET)


def test_teacher_and_student_access_tokens_are_not_interchangeable() -> None:
    teacher = create_access_token(1, JWT_SECRET, 5, "version")
    student = create_student_access_token(1, JWT_SECRET, "version", 1)
    with pytest.raises(jwt.InvalidTokenError, match="Unexpected token type"):
        decode_student_access_token(teacher, JWT_SECRET)
    with pytest.raises(jwt.InvalidTokenError, match="Unexpected token type"):
        decode_access_token(student, JWT_SECRET)


def test_a_tampered_access_token_is_refused() -> None:
    token = create_access_token(1, JWT_SECRET, 5, "version")
    header, payload, signature = token.split(".")
    forged = jwt.encode(claims("access", sub="2"), OTHER_SECRET, algorithm="HS256")
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(f"{header}.{forged.split('.')[1]}.{signature}", JWT_SECRET)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token, OTHER_SECRET)


@pytest.mark.parametrize("missing", ["sub", "type", "ver", "iat", "exp"])
def test_access_tokens_require_every_claim(missing: str) -> None:
    payload = claims("access")
    del payload[missing]
    token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
    with pytest.raises(jwt.MissingRequiredClaimError):
        decode_access_token(token, JWT_SECRET)


def test_a_non_numeric_subject_is_refused() -> None:
    token = jwt.encode(claims("access", sub="admin"), JWT_SECRET, algorithm="HS256")
    with pytest.raises(ValueError, match="invalid literal"):
        decode_access_token(token, JWT_SECRET)


def test_an_ended_session_yields_an_already_expired_access_token() -> None:
    ended = int((datetime.now(UTC) - timedelta(minutes=1)).timestamp())
    token = create_access_token(1, JWT_SECRET, 5, "version", session_expires_at=ended)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token, JWT_SECRET)


@pytest.mark.parametrize("purpose", ["two_factor_setup", "two_factor_verification"])
def test_two_factor_tokens_round_trip(purpose: str) -> None:
    token, token_hash, expires_at = create_two_factor_token(7, JWT_SECRET, purpose)
    assert decode_two_factor_token(token, JWT_SECRET) == (7, purpose, token_hash)
    assert 0 < expires_at - datetime.now(UTC).timestamp() <= 300


def test_two_factor_tokens_refuse_other_purposes() -> None:
    token, _, _ = create_two_factor_token(7, JWT_SECRET, "access")
    with pytest.raises(jwt.InvalidTokenError, match="Unexpected token type"):
        decode_two_factor_token(token, JWT_SECRET)


@pytest.mark.parametrize("token_id", ["", 42])
def test_two_factor_tokens_require_a_token_identifier(token_id) -> None:
    token = jwt.encode(
        claims("two_factor_verification", jti=token_id), JWT_SECRET, algorithm="HS256"
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_two_factor_token(token, JWT_SECRET)


# --- Secrets and proofs -------------------------------------------------------


@pytest.mark.parametrize(
    ("encrypt", "decrypt"),
    [
        (encrypt_totp_secret, decrypt_totp_secret),
        (encrypt_student_password, decrypt_student_password),
    ],
)
def test_encrypted_secrets_round_trip_only_with_their_key(encrypt, decrypt) -> None:
    plaintext = "JBSWY3DPEHPK3PXP-é"
    first = encrypt(plaintext, JWT_SECRET)
    second = encrypt(plaintext, JWT_SECRET)
    # Fernet adds a random IV: the same secret never encrypts the same way twice.
    assert first != second
    assert decrypt(first, JWT_SECRET) == decrypt(second, JWT_SECRET) == plaintext
    with pytest.raises(InvalidToken):
        decrypt(first, OTHER_SECRET)
    with pytest.raises(InvalidToken):
        decrypt(first[:-4] + "AAAA", JWT_SECRET)


def test_refresh_proofs_depend_on_both_token_and_secret() -> None:
    proof = refresh_request_proof("token", JWT_SECRET)
    assert proof == refresh_request_proof("token", JWT_SECRET)
    assert proof != refresh_request_proof("token", OTHER_SECRET)
    assert proof != refresh_request_proof("token2", JWT_SECRET)
    # A proof is not the bare token hash an attacker could compute.
    assert proof != hash_refresh_token("token")
    assert len(hash_refresh_token("")) == 64


# --- TOTP ----------------------------------------------------------------------


TOTP_SECRET = pyotp.random_base32()
# Mid-step, so the frozen clock is nowhere near a 30-second boundary.
FROZEN_NOW = datetime(2026, 11, 3, 12, 0, 15, tzinfo=UTC)


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> int:
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return FROZEN_NOW if tz is None else FROZEN_NOW.astimezone(tz)

    monkeypatch.setattr(security, "datetime", FrozenDatetime)
    return pyotp.TOTP(TOTP_SECRET).timecode(FROZEN_NOW)


def code_at(counter: int) -> str:
    return pyotp.TOTP(TOTP_SECRET).generate_otp(counter)


@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_totp_accepts_one_step_of_clock_drift(frozen_clock: int, offset: int) -> None:
    counter = frozen_clock + offset
    assert verify_totp_code(TOTP_SECRET, code_at(counter), None) == counter


@pytest.mark.parametrize("offset", [-3, -2, 2, 3])
def test_totp_refuses_codes_beyond_one_step(frozen_clock: int, offset: int) -> None:
    assert verify_totp_code(TOTP_SECRET, code_at(frozen_clock + offset), None) is None


def test_totp_refuses_a_replayed_or_older_code(frozen_clock: int) -> None:
    current = code_at(frozen_clock)
    assert verify_totp_code(TOTP_SECRET, current, frozen_clock) is None
    assert verify_totp_code(TOTP_SECRET, current, frozen_clock + 1) is None
    assert (
        verify_totp_code(TOTP_SECRET, code_at(frozen_clock - 1), frozen_clock - 1)
        is None
    )
    # A code newer than the last used one is still fine.
    assert (
        verify_totp_code(TOTP_SECRET, code_at(frozen_clock + 1), frozen_clock)
        == frozen_clock + 1
    )


def test_totp_refuses_malformed_codes(frozen_clock: int) -> None:
    current = code_at(frozen_clock)
    for code in ("", current[:-1], f" {current}", f"{current}0", "abcdef"):
        assert verify_totp_code(TOTP_SECRET, code, None) is None


# --- Trusted day -----------------------------------------------------------------


def test_a_login_at_local_midnight_is_trusted_for_a_full_day() -> None:
    paris = ZoneInfo("Europe/Paris")
    now = datetime(2026, 11, 3, 0, 0, tzinfo=paris)
    assert end_of_trusted_day(now, "Europe/Paris") == datetime(
        2026, 11, 4, tzinfo=paris
    )


def test_the_short_spring_forward_day_ends_at_midnight() -> None:
    # Clocks go forward on 29 March 2026: that local day only lasts 23 hours.
    paris = ZoneInfo("Europe/Paris")
    now = datetime(2026, 3, 29, 0, 30, tzinfo=paris)
    end = end_of_trusted_day(now, "Europe/Paris")
    assert end == datetime(2026, 3, 30, tzinfo=paris)
    assert end - now.astimezone(UTC) == timedelta(hours=22, minutes=30)


def test_the_trusted_day_follows_the_browser_zone_not_utc() -> None:
    # 11:00 UTC is already 01:00 the next day in Kiribati (UTC+14).
    now = datetime(2026, 11, 3, 11, 0, tzinfo=UTC)
    kiritimati = ZoneInfo("Pacific/Kiritimati")
    assert end_of_trusted_day(now, "Pacific/Kiritimati") == datetime(
        2026, 11, 5, tzinfo=kiritimati
    )
    assert end_of_trusted_day(now, "Pacific/Kiritimati") - now <= (
        TWO_FACTOR_TRUST_MAXIMUM
    )


# --- Rate limiters (database) ----------------------------------------------------


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    now = [1_800_000_000]
    monkeypatch.setattr(rate_limit, "time", lambda: now[0])
    return now


def stored_attempts(session: Session) -> list[int]:
    return list(session.scalars(select(LoginRateLimit.attempts)))


def test_the_login_limiter_allows_exactly_its_limit(
    session_factory: sessionmaker[Session], clock: list[int]
) -> None:
    limiter = LoginRateLimiter(3, 60, JWT_SECRET)
    with session_factory() as session:
        assert [limiter.reserve(session, "alice") for _ in range(3)] == [0, 0, 0]
        assert limiter.reserve(session, "alice") == 60
        clock[0] += 45
        assert limiter.reserve(session, "alice") == 15
        # Refused attempts are released: they never push the count past the
        # limit, so a successful step frees exactly one attempt.
        assert stored_attempts(session) == [3]
        limiter.release(session, "alice")
        assert limiter.reserve(session, "alice") == 0
        assert limiter.reserve(session, "alice") > 0


def test_the_login_limiter_resets_when_its_window_ends(
    session_factory: sessionmaker[Session], clock: list[int]
) -> None:
    limiter = LoginRateLimiter(1, 60, JWT_SECRET)
    with session_factory() as session:
        assert limiter.reserve(session, "alice") == 0
        clock[0] += 59
        assert limiter.reserve(session, "alice") == 1
        clock[0] += 1
        assert limiter.reserve(session, "alice") == 0


def test_releasing_never_goes_below_zero(
    session_factory: sessionmaker[Session], clock: list[int]
) -> None:
    limiter = LoginRateLimiter(2, 60, JWT_SECRET)
    with session_factory() as session:
        limiter.release(session, "nobody")
        assert stored_attempts(session) == []
        limiter.reserve(session, "alice")
        limiter.release(session, "alice")
        limiter.release(session, "alice")
        assert stored_attempts(session) == [0]
        # Extra releases bank no credit: the limit still applies in full.
        assert [limiter.reserve(session, "alice") for _ in range(3)] == [0, 0, 60]


def test_clearing_a_subject_restores_its_attempts(
    session_factory: sessionmaker[Session], clock: list[int]
) -> None:
    limiter = LoginRateLimiter(1, 60, JWT_SECRET)
    with session_factory() as session:
        limiter.reserve(session, "alice")
        assert limiter.reserve(session, "alice") > 0
        limiter.clear_subject(session, "alice")
        assert limiter.reserve(session, "alice") == 0


def test_limiters_keep_subjects_and_namespaces_apart(
    session_factory: sessionmaker[Session], clock: list[int]
) -> None:
    short = LoginRateLimiter(1, 60, JWT_SECRET)
    daily = LoginRateLimiter(1, 86400, JWT_SECRET, namespace="daily")
    with session_factory() as session:
        assert short.reserve(session, "alice") == 0
        assert short.reserve(session, "bob") == 0
        assert daily.reserve(session, "alice") == 0
        # The short window expiring purges its own namespace only.
        clock[0] += 61
        assert short.reserve(session, "carol") == 0
        assert daily.reserve(session, "alice") > 0


def test_limiter_buckets_depend_on_the_secret() -> None:
    first = LoginRateLimiter(1, 60, JWT_SECRET)
    second = LoginRateLimiter(1, 60, OTHER_SECRET)
    key = first._account_key("alice")
    assert key.startswith("account:")
    assert len(key) == len("account:") + LoginRateLimiter.BUCKET_HEX_CHARACTERS
    assert key != second._account_key("alice")
    assert key == first._account_key("alice")


def test_the_public_limiter_keeps_counting_refusals(
    session_factory: sessionmaker[Session], clock: list[int]
) -> None:
    limiter = FixedWindowRateLimiter(2, 60, "join")
    with session_factory() as session:
        assert [limiter.reserve(session, "10.0.0.1") for _ in range(4)] == [
            0,
            0,
            60,
            60,
        ]
        assert stored_attempts(session) == [4]
        assert limiter.reserve(session, "10.0.0.2") == 0
        clock[0] += 60
        assert limiter.reserve(session, "10.0.0.1") == 0


# --- Search and pagination -------------------------------------------------------


def test_search_patterns_for_empty_or_wildcard_only_input() -> None:
    assert contains_pattern("") == "%%"
    assert contains_pattern("%%") == r"%\%\%%"
    assert contains_pattern("\\%") == r"%\\\%%"


@pytest.mark.parametrize(
    "query",
    [
        "page=0",
        "page=-1",
        "page=abc",
        "page_size=0",
        f"page_size={MAX_PAGE_SIZE + 1}",
        "page_size=1.5",
    ],
)
def test_out_of_range_pagination_is_refused(tmp_path: Path, query: str) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        headers = login_admin(client)
        response = client.get(f"/api/admin/users?{query}", headers=headers)
        assert response.status_code == 422


def test_pages_past_the_end_are_empty_but_keep_the_total(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        headers = login_admin(client)
        full = client.get(
            f"/api/admin/users?page_size={MAX_PAGE_SIZE}", headers=headers
        )
        assert full.status_code == 200
        assert full.headers["X-Page-Size"] == str(MAX_PAGE_SIZE)
        total = full.headers["X-Total-Count"]
        assert int(total) == len(full.json()) >= 1

        beyond = client.get("/api/admin/users?page=1000", headers=headers)
        assert beyond.status_code == 200
        assert beyond.json() == []
        assert beyond.headers["X-Page"] == "1000"
        assert beyond.headers["X-Total-Count"] == total


ADMIN_LISTS = ["/api/admin/users", "/api/problem-reports"]
PROFESSOR_LISTS = [
    "/api/classes",
    "/api/question-banks",
    "/api/quizzes",
    "/api/quizzes/sessions/results",
    "/api/students",
]


@pytest.mark.parametrize("page", [MAX_PAGE + 1, 2**62, 10**30])
def test_an_overflowing_page_is_refused_on_every_list(
    tmp_path: Path, page: int
) -> None:
    """An unbounded page overflowed the bigint OFFSET and failed with a 500."""
    with make_client(settings_for(tmp_path / "test.db")) as client:
        admin_headers = login_admin(client)
        _, professor_headers = create_professor(client, admin_headers)
        for path, headers in [
            *((path, admin_headers) for path in ADMIN_LISTS),
            *((path, professor_headers) for path in PROFESSOR_LISTS),
        ]:
            response = client.get(f"{path}?page={page}", headers=headers)
            assert response.status_code == 422, path


def test_the_last_allowed_page_is_served_empty(tmp_path: Path) -> None:
    with make_client(settings_for(tmp_path / "test.db")) as client:
        admin_headers = login_admin(client)
        _, professor_headers = create_professor(client, admin_headers)
        for path, headers in [
            *((path, admin_headers) for path in ADMIN_LISTS),
            *((path, professor_headers) for path in PROFESSOR_LISTS),
        ]:
            response = client.get(
                f"{path}?page={MAX_PAGE}&page_size={MAX_PAGE_SIZE}", headers=headers
            )
            assert response.status_code == 200, path
            assert response.json() == [], path

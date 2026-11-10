"""Opaque choice identifiers for students.

Choice rows are numbered in the order the teacher wrote them, and teachers
often write the right answer first: a student who saw the real ids could sort
the shuffled choices back into that order. Students therefore only ever see,
send and address a choice through a token that is unique to their
participation and reveals nothing about its row.

A token is an HMAC of (session, participant, choice) under a key derived from
the JWT secret at startup and attached to every database session
(create_app). Teacher-facing payloads and stored answers keep real ids.

Trainings use the same tokens, including in their immediate feedback: they
reveal the key anyway once a question is answered, but one code path for
every student payload is simpler to keep right.
"""

from collections.abc import Iterable

from sqlalchemy.orm import Session

from app.models import QuestionChoice, QuizParticipant, QuizSession
from app.security import student_choice_token

CHOICE_HMAC_ENTRY = "student_choice_hmac"


class ChoiceTokens:
    """The tokens one participant sees for the choices of their questions."""

    def __init__(
        self,
        session: Session,
        quiz_session: QuizSession,
        participant: QuizParticipant,
    ) -> None:
        self._key: bytes = session.info[CHOICE_HMAC_ENTRY]
        self._session_id = quiz_session.id
        self._participant_id = participant.id

    def token(self, choice_id: int) -> str:
        return student_choice_token(
            self._key, self._session_id, self._participant_id, choice_id
        )

    def choice_ids(
        self, tokens: Iterable[str], choices: Iterable[QuestionChoice]
    ) -> list[int] | None:
        """The choices the tokens name, in order; None if one names none."""
        choice_ids_by_token = {self.token(choice.id): choice.id for choice in choices}
        resolved = [choice_ids_by_token.get(token) for token in tokens]
        if any(choice_id is None for choice_id in resolved):
            return None
        return [choice_id for choice_id in resolved if choice_id is not None]

"""Answers to a running quiz: which ones a participant may give, and storing them.

The guards reject an answer, a review or a submission the session, the
participant or the quiz does not allow; the rest validates an answer against
its question, stores it and moves the participant on.
"""

import json
from datetime import UTC, datetime

from fastapi import status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.choice_tokens import ChoiceTokens
from app.enums import AnswerMode, QuizMode, SessionStatus
from app.errors import ApiError, ErrorCode
from app.models import (
    Question,
    QuestionChoice,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
)
from app.question_responses import load_question_records
from app.schemas import StudentQuizAnswer, TrainingFeedback
from app.services.grading import decoded_answer_data
from app.services.question_assignments import (
    current_question_id,
    last_answered_question_id,
    session_question_ids,
)
from app.services.session_lifecycle import (
    active_exam_bank_ids_for_class,
    answer_review_enabled,
    answered_question_ids,
)


def require_answer_accepted(
    quiz_session: QuizSession, participant: QuizParticipant, session: Session
) -> None:
    """Reject an answer the session, the student or an exam does not allow."""
    # "finished" is allowed past this gate only so a repeat of the last answer
    # can still be recognised below: a double click or a network retry can
    # arrive after the first submission finished the session, and must get
    # the same answer back rather than an error. Any other non-"in_progress"
    # status (paused included) still rejects outright.
    if quiz_session.status not in (SessionStatus.IN_PROGRESS, SessionStatus.FINISHED):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_NOT_ACCEPTING_ANSWERS,
            "Le quiz n’accepte pas de réponses actuellement",
        )
    if participant.student_id is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_STUDENT_REMOVED,
            "L’élève n’existe plus",
        )
    if (
        quiz_session.training_question_bank_id is not None
        and quiz_session.class_id is not None
        and quiz_session.training_question_bank_id
        in active_exam_bank_ids_for_class(quiz_session.class_id, session)
    ):
        # Opening an exam discards these trainings; this also covers one
        # started concurrently, which must not give feedback during the exam.
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.TRAINING_BLOCKED_BY_EXAM,
            "Cet entraînement est indisponible pendant un examen",
        )


def answered_question(
    quiz_session: QuizSession, participant: QuizParticipant, session: Session
) -> tuple[Question, list[QuestionChoice], bool]:
    """The question an answer is for, its choices, and whether it is retargeted.

    A participant who already answered everything has no current question;
    the answer is then retargeted at their last one, so that a repeat of
    their final answer can be recognised.
    """
    question_id = current_question_id(quiz_session, participant, session)
    retargeting_finished_answer = question_id is None
    if retargeting_finished_answer:
        question_id = last_answered_question_id(quiz_session, participant, session)
    if question_id is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_NO_CURRENT_QUESTION,
            "Aucune question en cours",
        )
    questions_by_id, choices_by_question = load_question_records([question_id], session)
    question = questions_by_id.get(question_id)
    if question is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_QUESTION_UNAVAILABLE,
            "La question actuelle n’est pas disponible",
        )
    return (
        question,
        choices_by_question.get(question_id, []),
        retargeting_finished_answer,
    )


def validated_answer(
    payload: StudentQuizAnswer,
    question: Question,
    choices: list[QuestionChoice],
    quiz: Quiz,
    tokens: ChoiceTokens,
) -> tuple[dict[str, object], TrainingFeedback | None]:
    """The answer to store, and the immediate feedback a training gives.

    The student names choices by their tokens; the stored answer holds the
    real choice ids.
    """
    feedback: TrainingFeedback | None = None
    if question.answer_mode == AnswerMode.WRITTEN:
        written_answer = (payload.written_answer or "").strip()
        if not written_answer or payload.selected_choice_ids is not None:
            raise ApiError(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                ErrorCode.ANSWER_WRITTEN_REQUIRED,
                "Une réponse rédactionnelle est requise",
            )
        answer_data: dict[str, object] = {"written_answer": written_answer}
        expected_answer = next(
            (choice.label for choice in choices if choice.is_correct),
            "",
        )
        if quiz.mode == QuizMode.TRAINING:
            feedback = TrainingFeedback(
                question_id=question.id,
                is_correct=None,
                correct_choice_ids=[],
                expected_answer=expected_answer,
                submitted_answer=written_answer,
                requires_manual_review=True,
            )
        return answer_data, feedback
    if payload.selected_choice_ids is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.ANSWER_CHOICE_REQUIRED,
            "Au moins une proposition doit être sélectionnée",
        )
    selected_tokens = list(dict.fromkeys(payload.selected_choice_ids or []))
    if payload.written_answer is not None or (
        question.answer_mode == AnswerMode.SINGLE
        and question.answer_mode_disclosed
        and len(selected_tokens) != 1
    ):
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.ANSWER_MODE_MISMATCH,
            "La réponse envoyée ne correspond pas au type de la question",
        )
    selected_ids = tokens.choice_ids(selected_tokens, choices)
    if selected_ids is None:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            ErrorCode.ANSWER_CHOICE_INVALID,
            "Une proposition sélectionnée est invalide",
        )
    if quiz.mode == QuizMode.TRAINING:
        correct_ids = [choice.id for choice in choices if choice.is_correct]
        feedback = TrainingFeedback(
            question_id=question.id,
            is_correct=set(selected_ids) == set(correct_ids),
            correct_choice_ids=[tokens.token(choice_id) for choice_id in correct_ids],
        )
    return {"selected_choice_ids": selected_ids}, feedback


def require_same_finished_answer(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    question_id: int,
    answer_data: dict[str, object],
    session: Session,
) -> None:
    """Accept a retargeted answer only as a duplicate of the recorded one.

    The participant already moved past this question: the submission must
    match what an earlier copy of it already recorded, rather than silently
    rewrite a finished answer.
    """
    existing_answer = session.scalar(
        select(QuizAnswer).where(
            QuizAnswer.session_id == quiz_session.id,
            QuizAnswer.participant_id == participant.id,
            QuizAnswer.question_id == question_id,
        )
    )
    if existing_answer is None or decoded_answer_data(existing_answer) != answer_data:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_NO_CURRENT_QUESTION,
            "Aucune question en cours",
        )


def store_answer(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    question_id: int,
    answer_data: dict[str, object],
    session: Session,
) -> None:
    # Atomic upsert: concurrent submissions for the same question can never
    # create duplicate answers nor crash on the uniqueness constraint.
    answer_statement = insert(QuizAnswer).values(
        session_id=quiz_session.id,
        participant_id=participant.id,
        question_id=question_id,
        answer_data=json.dumps(answer_data, ensure_ascii=False),
        score=0,
        is_graded=False,
    )
    session.execute(
        answer_statement.on_conflict_do_update(
            index_elements=[
                QuizAnswer.session_id,
                QuizAnswer.participant_id,
                QuizAnswer.question_id,
            ],
            set_={
                "answer_data": answer_statement.excluded.answer_data,
                "score": 0,
                "is_graded": False,
            },
        )
    )


def advance_participant(
    quiz_session: QuizSession,
    quiz: Quiz,
    participant: QuizParticipant,
    session: Session,
) -> None:
    """Move to the next question, or past the last one."""
    total_questions = len(session_question_ids(quiz_session, session, participant))
    if (
        participant.current_position is not None
        and participant.current_position + 1 < total_questions
    ):
        participant.current_position += 1
    else:
        participant.current_position = None
    if (
        participant.current_position is None
        and participant.submitted_at is None
        and not answer_review_enabled(quiz_session, quiz)
    ):
        # Without the review step the last answer is the final submission.
        participant.submitted_at = datetime.now(UTC)


def require_answer_review_offered(quiz_session: QuizSession, quiz: Quiz) -> None:
    """Reject a review request on a quiz that has no final submission step."""
    if not answer_review_enabled(quiz_session, quiz):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_REVIEW_UNAVAILABLE,
            "La relecture des réponses n’est pas disponible",
        )


def require_reviewable_participant(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: Session,
) -> None:
    """Reject a participant who may not reach the answer review step.

    The session must still be running and every assigned question must already
    have an answer.
    """
    if quiz_session.status != SessionStatus.IN_PROGRESS:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_REVIEW_UNAVAILABLE,
            "La relecture des réponses n’est pas disponible",
        )
    question_ids = session_question_ids(quiz_session, session, participant)
    answered_ids = answered_question_ids(quiz_session, participant, session)
    if not question_ids or not set(question_ids).issubset(answered_ids):
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_ANSWERS_INCOMPLETE,
            "Toutes les questions doivent être répondues",
        )

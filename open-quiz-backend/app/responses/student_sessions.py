"""Response bodies describing a quiz session to the student taking it.

The state of the session for one participant, their current question with
its choices behind opaque tokens, and the summary of their answers before
the final submission.
"""

from hashlib import sha256

from fastapi import status
from sqlalchemy import select

from app.core.dependencies import DbSession
from app.core.errors import ApiError, ErrorCode
from app.domain.choice_tokens import ChoiceTokens
from app.domain.class_names import format_class_name
from app.enums import AnswerMode, QuizMode, SessionStatus
from app.models import (
    Question,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    StudentClass,
)
from app.records.questions import load_question_records
from app.schemas.student_quizzes import (
    StudentAnswerSummary,
    StudentQuizChoiceResponse,
    StudentQuizQuestionResponse,
    StudentQuizSessionResponse,
    StudentQuizStateResponse,
)
from app.services.grading import (
    decoded_answer_data,
    question_maximum_scores,
    training_result,
)
from app.services.question_assignments import (
    accessible_question_positions,
    current_question_id,
    session_question_ids,
)
from app.services.session_lifecycle import (
    answered_question_ids,
    final_review_offered,
    previous_questions_allowed,
    quiz_ends_at,
)


def student_session_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    participant: QuizParticipant,
    session: DbSession,
) -> StudentQuizSessionResponse:
    return StudentQuizSessionResponse(
        quiz_title=quiz_session.quiz_title or quiz.title,
        source_language=quiz_session.source_language or quiz.source_language,
        class_name=quiz_session_class_name(quiz_session, session),
        student_name=(
            participant.student_display_name or participant.student_identifier
        ),
        join_code=quiz_session.join_code,
        status=quiz_session.status,
        ends_at=quiz_ends_at(quiz_session, quiz),
    )


def quiz_session_class_name(quiz_session: QuizSession, session: DbSession) -> str:
    if quiz_session.class_id is None:
        return quiz_session.class_name
    student_class = session.get(StudentClass, quiz_session.class_id)
    if student_class is None:
        return quiz_session.class_name
    return format_class_name(student_class.grade_level, student_class.name)


def public_answer_mode(question: Question) -> str:
    """The answer mode a student may see.

    Hidden choice modes must have the same API and control shape. The server
    still validates and grades against the real stored mode.
    """
    if not question.answer_mode_disclosed and question.answer_mode in {
        AnswerMode.SINGLE,
        AnswerMode.MULTIPLE,
    }:
        return AnswerMode.MULTIPLE
    return question.answer_mode


def student_answer_summaries(
    quiz_session: QuizSession,
    participant: QuizParticipant,
    question_ids: list[int],
    session: DbSession,
) -> list[StudentAnswerSummary]:
    """What a participant answered, for the review before final submission.

    Skipped questions still unanswered are listed with no answer.

    Only the participant's own wording is returned: nothing here discloses the
    expected answer of a question that is still running for the class.
    """
    answers = {
        answer.question_id: answer
        for answer in session.scalars(
            select(QuizAnswer).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    }
    questions_by_id, choices_by_question = load_question_records(question_ids, session)
    summaries: list[StudentAnswerSummary] = []
    for position, question_id in enumerate(question_ids):
        question = questions_by_id.get(question_id)
        answer = answers.get(question_id)
        if question is None or (
            answer is None and question_id not in participant.skipped_question_ids
        ):
            continue
        # A skipped question still unanswered is listed with no answer.
        submitted = decoded_answer_data(answer) if answer is not None else {}
        if question.answer_mode == AnswerMode.WRITTEN:
            submitted_answers = [str(submitted.get("written_answer", ""))]
        else:
            choices_by_id = {
                choice.id: choice for choice in choices_by_question.get(question_id, [])
            }
            submitted_ids = submitted.get("selected_choice_ids", [])
            if not isinstance(submitted_ids, list):
                submitted_ids = []
            submitted_answers = [
                choices_by_id[choice_id].label
                for choice_id in submitted_ids
                if type(choice_id) is int and choice_id in choices_by_id
            ]
        summaries.append(
            StudentAnswerSummary(
                question_number=position + 1,
                question_id=question.id,
                prompt=question.prompt,
                answer_mode=public_answer_mode(question),
                submitted_answers=submitted_answers,
            )
        )
    return summaries


def student_question_response(
    question_id: int,
    quiz_session: QuizSession,
    participant: QuizParticipant,
    session: DbSession,
    *,
    include_points: bool = False,
) -> StudentQuizQuestionResponse:
    questions_by_id, choices_by_question = load_question_records([question_id], session)
    question = questions_by_id.get(question_id)
    if question is None:
        raise ApiError(
            status.HTTP_409_CONFLICT,
            ErrorCode.QUIZ_QUESTION_UNAVAILABLE,
            "La question actuelle n’est pas disponible",
        )
    choices = (
        []
        if question.answer_mode == AnswerMode.WRITTEN
        else choices_by_question.get(question.id, [])
    )
    choices.sort(
        key=lambda choice: sha256(
            (f"{quiz_session.id}:{participant.id}:{question.id}:{choice.id}").encode()
        ).digest()
    )
    tokens = ChoiceTokens(session, quiz_session, participant)
    code = session.get(QuestionCode, question.id)
    return StudentQuizQuestionResponse(
        id=question.id,
        prompt=question.prompt,
        difficulty=question.difficulty,
        answer_mode=public_answer_mode(question),
        answer_mode_disclosed=question.answer_mode_disclosed,
        response_language=question.response_language,
        allow_code_execution=question.allow_code_execution,
        has_image=question.image_sha256 is not None,
        code_language=code.language if code else None,
        code_content=code.content if code else None,
        choices=[
            StudentQuizChoiceResponse(
                id=tokens.token(choice.id),
                label=choice.label,
                position=position,
                has_image=choice.image_sha256 is not None,
                code_language=choice.code_language,
                code_content=choice.code_content,
            )
            for position, choice in enumerate(choices)
        ],
        total_points=(
            question_maximum_scores([question.id], session).get(question.id)
            if include_points
            else None
        ),
    )


def student_state_response(
    quiz_session: QuizSession,
    quiz: Quiz,
    participant: QuizParticipant,
    session: DbSession,
) -> StudentQuizStateResponse:
    question_ids = session_question_ids(quiz_session, session, participant)
    question_id = current_question_id(quiz_session, participant, session)
    answered_ids = answered_question_ids(quiz_session, participant, session)
    # A skipped question has no answer, but the participant is done with it.
    handed_in = answered_ids | set(participant.skipped_question_ids)
    # A participant who has submitted every assigned answer has no current
    # question while classmates may still be working. Keep that completed
    # state explicit so the frontend can render its waiting message instead of
    # an otherwise empty in-progress page.
    has_answered = (
        question_id in answered_ids
        if question_id is not None
        else bool(question_ids) and set(question_ids).issubset(handed_in)
    )
    existing_answer = (
        session.scalar(
            select(QuizAnswer).where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
                QuizAnswer.question_id == question_id,
            )
        )
        if question_id is not None
        else None
    )
    saved_answer = (
        decoded_answer_data(existing_answer) if existing_answer is not None else {}
    )
    saved_choice_ids = saved_answer.get("selected_choice_ids")
    tokens = ChoiceTokens(session, quiz_session, participant)
    answered_count = len(answered_ids)
    # Skipped questions left unanswered offer the review step as well.
    review_enabled = final_review_offered(quiz_session, quiz, participant, session)
    # A participant done with every question (answered or skipped) but who
    # has not confirmed yet keeps
    # the session open for themselves: they may re-read, and correct when the
    # quiz allows going back, until they submit their paper.
    awaiting_final_submission = (
        review_enabled
        and quiz_session.status in (SessionStatus.IN_PROGRESS, SessionStatus.PAUSED)
        and participant.submitted_at is None
        and participant.current_position is None
        and bool(question_ids)
        and set(question_ids).issubset(handed_in)
    )
    accessible_positions = accessible_question_positions(
        question_ids,
        handed_in,
        participant.current_position,
    )
    state = StudentQuizStateResponse(
        **student_session_response(
            quiz_session, quiz, participant, session
        ).model_dump(),
        question_number=(
            participant.current_position + 1
            if participant.current_position is not None
            and quiz_session.status == SessionStatus.IN_PROGRESS
            else None
        ),
        total_questions=len(question_ids),
        has_answered=has_answered,
        answered_count=answered_count,
        allow_previous_questions=previous_questions_allowed(quiz_session, quiz),
        allow_answer_review=review_enabled,
        awaiting_final_submission=awaiting_final_submission,
        answer_summaries=(
            student_answer_summaries(quiz_session, participant, question_ids, session)
            if awaiting_final_submission
            else []
        ),
        accessible_question_numbers=[
            position + 1 for position in sorted(accessible_positions)
        ],
        answered_question_numbers=[
            position + 1
            for position, answered_id in enumerate(question_ids)
            if answered_id in answered_ids
        ],
        skipped_question_numbers=[
            position + 1
            for position, skipped_id in enumerate(question_ids)
            if skipped_id in participant.skipped_question_ids
        ],
        selected_choice_ids=(
            [
                tokens.token(choice_id)
                for choice_id in saved_choice_ids
                if type(choice_id) is int
            ]
            if isinstance(saved_choice_ids, list)
            else None
        ),
        written_answer=saved_answer.get("written_answer"),
        question=(
            student_question_response(
                question_id,
                quiz_session,
                participant,
                session,
                include_points=quiz.mode == QuizMode.EXAM,
            )
            if question_id is not None
            and quiz_session.status == SessionStatus.IN_PROGRESS
            else None
        ),
    )
    if quiz.mode == QuizMode.TRAINING and quiz_session.status == SessionStatus.FINISHED:
        score, maximum, pending = training_result(quiz_session, participant, session)
        state.potential_score = score
        state.potential_maximum_score = maximum
        state.pending_manual_review_count = pending
    return state

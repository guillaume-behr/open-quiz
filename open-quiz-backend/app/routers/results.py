"""Quiz results: finished sessions, their export, grading and publication.

Teachers list and export the results of their finished sessions, read each
participant's answers, grade written answers and publish the grades; students
list their own published results.
"""

from collections import defaultdict
from datetime import UTC, datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    Response,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select

from app.audit import audit_event
from app.class_names import format_class_name
from app.dependencies import DbSession, ProfessorUser
from app.errors import ErrorCode, api_error
from app.models import (
    Question,
    QuestionChoice,
    QuestionCode,
    Quiz,
    QuizAnswer,
    QuizParticipant,
    QuizSession,
    Student,
    StudentAccount,
    StudentClass,
)
from app.pagination import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, set_pagination_headers
from app.question_responses import load_question_records
from app.routers.quizzes import (
    owned_quiz_session,
    purge_expired_quiz_results,
    session_response,
)
from app.routers.student_auth import current_student
from app.schemas import (
    QuizAnswerGrade,
    QuizAnswerReview,
    QuizSessionResponse,
    StudentQuizHistoryAnswer,
    StudentQuizHistoryItem,
)
from app.services.grading import (
    decoded_answer_data,
    question_maximum_scores,
    selected_choice_ids,
    session_question_points,
)
from app.services.question_assignments import (
    assigned_question_ids,
    load_session_question_assignments,
    session_question_ids,
)
from app.services.results import finished_session_responses, stream_results_csv
from app.services.session_lifecycle import (
    expire_owned_quiz_sessions,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


@router.get("/sessions/results", response_model=list[QuizSessionResponse])
def list_quiz_results(
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
    response: Response,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
    quiz_search: Annotated[str, Query(max_length=160)] = "",
    class_search: Annotated[str, Query(max_length=120)] = "",
) -> list[QuizSessionResponse]:
    expire_owned_quiz_sessions(professor, session)
    purge_expired_quiz_results(professor, request, session)
    filters = [
        Quiz.owner_id == professor.id,
        Quiz.mode == "exam",
        QuizSession.status == "finished",
    ]
    if quiz_search:
        filters.append(
            func.coalesce(QuizSession.quiz_title, Quiz.title).ilike(f"%{quiz_search}%")
        )
    if class_search:
        filters.append(QuizSession.class_name.ilike(f"%{class_search}%"))
    total = (
        session.scalar(
            select(func.count())
            .select_from(QuizSession)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(*filters)
        )
        or 0
    )
    set_pagination_headers(response, page=page, page_size=page_size, total=total)
    rows = list(
        session.execute(
            select(QuizSession, Quiz)
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(*filters)
            .order_by(
                QuizSession.started_at.desc(),
                QuizSession.created_at.desc(),
                QuizSession.id.desc(),
            )
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return finished_session_responses(rows, session)


@router.get("/sessions/results/export")
def export_quiz_results(
    request: Request,
    professor: ProfessorUser,
    session: DbSession,
    class_id: Annotated[int, Query(ge=1)],
    quiz_id: Annotated[int | None, Query(ge=1)] = None,
) -> StreamingResponse:
    purge_expired_quiz_results(professor, request, session)
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error(ErrorCode.CLASS_NOT_FOUND, "Classe introuvable"),
        )

    if quiz_id is not None:
        quiz = session.scalar(
            select(Quiz).where(Quiz.id == quiz_id, Quiz.owner_id == professor.id)
        )
        if quiz is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=api_error(ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable"),
            )
    safe_class_id = student_class.id
    safe_quiz = f"-quiz-{quiz_id}" if quiz_id is not None else "-tous-les-quiz"
    filename = f"resultats-classe-{safe_class_id}{safe_quiz}.csv"
    return StreamingResponse(
        stream_results_csv(
            request.app.state.session_factory, professor.id, class_id, quiz_id
        ),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def answer_review(
    answer: QuizAnswer,
    question: Question,
    position: int,
    choices: list[QuestionChoice],
    max_score: float,
    code: QuestionCode | None = None,
) -> QuizAnswerReview:
    submitted = decoded_answer_data(answer)
    choices_by_id = {choice.id: choice for choice in choices}
    if question.answer_mode == "written":
        submitted_answers = [str(submitted.get("written_answer", ""))]
        is_correct = (
            answer.score >= max_score if answer.is_graded and max_score > 0 else None
        )
    else:
        submitted_ids = submitted.get("selected_choice_ids", [])
        if not isinstance(submitted_ids, list):
            submitted_ids = []
        # Only real integers can name a choice, and labels are looked up by id.
        submitted_ids = [
            choice_id for choice_id in submitted_ids if type(choice_id) is int
        ]
        submitted_answers = [
            choices_by_id[choice_id].label
            for choice_id in submitted_ids
            if choice_id in choices_by_id
        ]
        is_correct = set(submitted_ids) == {
            choice.id for choice in choices if choice.is_correct
        }
    expected_answers = [choice.label for choice in choices if choice.is_correct]
    return QuizAnswerReview(
        id=answer.id,
        question_id=question.id,
        position=position + 1,
        prompt=question.prompt,
        difficulty=question.difficulty,
        answer_mode=question.answer_mode,
        code_content=code.content if code else None,
        code_language=code.language if code else None,
        response_language=question.response_language,
        submitted_answers=submitted_answers,
        expected_answers=expected_answers,
        score=answer.score,
        max_score=max_score,
        is_graded=answer.is_graded,
        is_correct=is_correct,
        feedback=answer.feedback,
    )


@router.get(
    "/sessions/{session_id}/participants/{participant_id}/answers",
    response_model=list[QuizAnswerReview],
)
def list_participant_answers(
    session_id: int,
    participant_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuizAnswerReview]:
    quiz_session, _ = owned_quiz_session(session_id, professor, session)
    if quiz_session.status != "finished":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_SESSION_NOT_FINISHED,
                "Les réponses sont disponibles une fois le quiz terminé",
            ),
        )
    participant = session.scalar(
        select(QuizParticipant).where(
            QuizParticipant.id == participant_id,
            QuizParticipant.session_id == quiz_session.id,
        )
    )
    if participant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error(
                ErrorCode.PARTICIPANT_NOT_FOUND, "Participant introuvable"
            ),
        )
    rows = list(
        session.execute(
            select(QuizAnswer, Question)
            .join(Question, Question.id == QuizAnswer.question_id)
            .where(
                QuizAnswer.session_id == quiz_session.id,
                QuizAnswer.participant_id == participant.id,
            )
        )
    )
    if (
        participant.left_at is not None
        and (
            quiz_session.started_at is None
            or participant.left_at <= quiz_session.started_at
        )
        and len(rows) == 0
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error(
                ErrorCode.PARTICIPANT_NOT_FOUND, "Participant introuvable"
            ),
        )
    question_order = {
        question_id: position
        for position, question_id in enumerate(
            session_question_ids(quiz_session, session, participant)
        )
    }
    question_points = session_question_points(quiz_session, session, participant)
    rows.sort(key=lambda row: question_order.get(row[1].id, len(question_order)))
    question_ids = [question.id for _, question in rows]
    choices_by_question: dict[int, list[QuestionChoice]] = defaultdict(list)
    codes_by_question: dict[int, QuestionCode] = {}
    if question_ids:
        for choice in session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id.in_(question_ids))
            .order_by(QuestionChoice.position, QuestionChoice.id)
        ):
            choices_by_question[choice.question_id].append(choice)
        for code in session.scalars(
            select(QuestionCode).where(QuestionCode.question_id.in_(question_ids))
        ):
            codes_by_question[code.question_id] = code
    return [
        answer_review(
            answer,
            question,
            question_order.get(question.id, 0),
            choices_by_question[question.id],
            question_points.get(question.id, 0),
            codes_by_question.get(question.id),
        )
        for answer, question in rows
    ]


@router.get(
    "/student/results",
    response_model=list[StudentQuizHistoryItem],
)
def list_student_quiz_history(
    student: Annotated[StudentAccount, Depends(current_student)],
    session: DbSession,
) -> list[StudentQuizHistoryItem]:
    membership_ids = list(
        session.scalars(select(Student.id).where(Student.account_id == student.id))
    )
    if not membership_ids:
        return []
    rows = list(
        session.execute(
            select(QuizSession, QuizParticipant)
            .join(
                QuizParticipant,
                QuizParticipant.session_id == QuizSession.id,
            )
            .join(Quiz, Quiz.id == QuizSession.quiz_id)
            .where(
                QuizParticipant.student_id.in_(membership_ids),
                QuizSession.status == "finished",
                QuizSession.started_at.is_not(None),
                Quiz.mode == "exam",
            )
            .order_by(QuizSession.started_at.desc(), QuizSession.id.desc())
        )
    )
    session_ids = [quiz_session.id for quiz_session, _ in rows]
    participant_ids = [participant.id for _, participant in rows]
    (
        common_by_session,
        personalized_by_student,
        personalized_by_identifier,
    ) = load_session_question_assignments(session_ids, session)
    question_ids_by_participant: dict[int, list[int]] = {}
    all_question_ids: set[int] = set()
    for quiz_session, participant in rows:
        question_ids = assigned_question_ids(
            quiz_session.id,
            participant.student_id,
            participant.student_identifier,
            common_by_session,
            personalized_by_student,
            personalized_by_identifier,
        )
        question_ids_by_participant[participant.id] = question_ids
        all_question_ids.update(question_ids)
    questions_by_id, choices_by_question = load_question_records(
        all_question_ids, session
    )
    answers_by_participant_question = {
        (answer.participant_id, answer.question_id): answer
        for answer in session.scalars(
            select(QuizAnswer).where(QuizAnswer.participant_id.in_(participant_ids))
        )
    }
    question_points = question_maximum_scores(list(all_question_ids), session)
    class_ids = {
        quiz_session.class_id
        for quiz_session, _ in rows
        if quiz_session.class_id is not None
    }
    classes_by_id = {
        student_class.id: student_class
        for student_class in session.scalars(
            select(StudentClass).where(StudentClass.id.in_(class_ids))
        )
    }

    codes_by_question = {
        code.question_id: code
        for code in session.scalars(
            select(QuestionCode).where(QuestionCode.question_id.in_(all_question_ids))
        )
    }

    history: list[StudentQuizHistoryItem] = []
    for quiz_session, participant in rows:
        question_ids = question_ids_by_participant[participant.id]
        answers_by_question = {
            question_id: answers_by_participant_question.get(
                (participant.id, question_id)
            )
            for question_id in question_ids
        }
        answers = []
        for position, question_id in enumerate(question_ids):
            question = questions_by_id.get(question_id)
            if question is None:
                continue
            question_choices = choices_by_question[question.id]
            q_code = codes_by_question.get(question.id)
            answer = answers_by_question.get(question.id)
            review = None
            if answer is not None:
                review = answer_review(
                    answer,
                    question,
                    position,
                    question_choices,
                    question_points.get(question.id, 0),
                    q_code,
                )
                submitted_answers = review.submitted_answers
                score = review.score
                max_score = review.max_score
                if question.answer_mode == "written":
                    is_correct = (
                        (answer.score >= review.max_score)
                        if answer.is_graded and review.max_score > 0
                        else None
                    )
                else:
                    correct_ids = {
                        choice.id for choice in question_choices if choice.is_correct
                    }
                    is_correct = selected_choice_ids(answer) == correct_ids
            else:
                submitted_answers = []
                score = 0.0
                max_score = float(question_points.get(question.id, 0))
                is_correct = False
            answers.append(
                StudentQuizHistoryAnswer(
                    question_id=question.id,
                    position=position + 1,
                    prompt=question.prompt,
                    difficulty=question.difficulty,
                    answer_mode=question.answer_mode,
                    code_content=q_code.content if q_code else None,
                    code_language=q_code.language if q_code else None,
                    response_language=question.response_language,
                    submitted_answers=submitted_answers,
                    expected_answers=[
                        choice.label for choice in question_choices if choice.is_correct
                    ],
                    score=score,
                    max_score=max_score,
                    is_correct=is_correct,
                    feedback=review.feedback if review else None,
                )
            )
        history.append(
            StudentQuizHistoryItem(
                session_id=quiz_session.id,
                quiz_title=quiz_session.quiz_title or "Quiz",
                class_name=(
                    format_class_name(
                        classes_by_id[quiz_session.class_id].grade_level,
                        classes_by_id[quiz_session.class_id].name,
                    )
                    if quiz_session.class_id in classes_by_id
                    else quiz_session.class_name
                ),
                started_at=quiz_session.started_at,
                grades_published=quiz_session.grades_published_at is not None,
                score=round(
                    sum(
                        answer.score
                        for answer in answers_by_question.values()
                        if answer is not None
                    ),
                    2,
                ),
                maximum_score=round(
                    sum(
                        question_points.get(question_id, 0)
                        for question_id in question_ids
                    ),
                    2,
                ),
                answers=answers,
            )
        )
    return history


@router.post(
    "/sessions/{session_id}/publish-grades",
    response_model=QuizSessionResponse,
)
def publish_quiz_grades(
    session_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizSessionResponse:
    quiz_session, quiz = owned_quiz_session(session_id, professor, session)
    if quiz_session.status != "finished":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_SESSION_NOT_FINISHED,
                "Les notes ne peuvent être publiées qu'une fois le quiz terminé",
            ),
        )
    pending_count = session.scalar(
        select(func.count(QuizAnswer.id)).where(
            QuizAnswer.session_id == quiz_session.id,
            QuizAnswer.is_graded.is_(False),
        )
    )
    if pending_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.GRADES_PENDING,
                "Toutes les réponses doivent être corrigées avant publication",
            ),
        )
    if quiz_session.grades_published_at is None:
        quiz_session.grades_published_at = datetime.now(UTC)
        audit_event(
            "quiz.grades_published",
            professor_id=professor.id,
            session_id=quiz_session.id,
        )
        session.commit()
        session.refresh(quiz_session)
    return session_response(quiz_session, quiz, session)


@router.post(
    "/sessions/{session_id}/answers/{answer_id}/grade",
    response_model=QuizAnswerReview,
)
def grade_written_answer(
    session_id: int,
    answer_id: int,
    payload: QuizAnswerGrade,
    professor: ProfessorUser,
    session: DbSession,
) -> QuizAnswerReview:
    quiz_session, _ = owned_quiz_session(session_id, professor, session)
    if quiz_session.status != "finished":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.QUIZ_SESSION_NOT_FINISHED,
                "La correction est disponible une fois le quiz terminé",
            ),
        )
    if quiz_session.grades_published_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.GRADES_PUBLISHED,
                "Les notes publiées ne peuvent plus être modifiées",
            ),
        )
    row = session.execute(
        select(QuizAnswer, Question)
        .join(Question, Question.id == QuizAnswer.question_id)
        .where(
            QuizAnswer.id == answer_id,
            QuizAnswer.session_id == quiz_session.id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=api_error(ErrorCode.ANSWER_NOT_FOUND, "Réponse introuvable"),
        )
    answer, question = row
    participant = session.get(QuizParticipant, answer.participant_id)
    question_ids = (
        session_question_ids(quiz_session, session, participant)
        if participant is not None
        else []
    )
    if question.id not in question_ids:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=api_error(
                ErrorCode.ANSWER_QUESTION_NOT_IN_SESSION,
                "La question ne fait pas partie de cette session",
            ),
        )
    position = question_ids.index(question.id)
    if question.answer_mode != "written":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=api_error(
                ErrorCode.ANSWER_NOT_WRITTEN,
                "Seules les réponses rédactionnelles sont corrigées manuellement",
            ),
        )
    choices = list(
        session.scalars(
            select(QuestionChoice)
            .where(QuestionChoice.question_id == question.id)
            .order_by(QuestionChoice.position, QuestionChoice.id)
        )
    )
    max_score = session_question_points(quiz_session, session, participant).get(
        question.id, 0
    )
    if payload.score > max_score:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=api_error(
                ErrorCode.GRADE_ABOVE_MAXIMUM,
                f"La note ne peut pas dépasser {max_score:g}",
            ),
        )
    answer.score = payload.score
    answer.is_graded = True
    answer.feedback = (
        payload.feedback.strip()
        if payload.feedback and payload.feedback.strip()
        else None
    )
    session.commit()
    code = session.get(QuestionCode, question.id)
    return answer_review(answer, question, position, choices, max_score, code)

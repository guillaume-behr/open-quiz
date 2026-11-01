"""Training: question banks a class may practise freely, outside any exam.

Teachers choose which of their banks each class can train on; students list
them, review their past attempts and start a training quiz that gives
immediate feedback. A bank in use by an active exam of the class cannot be
trained on.
"""

from datetime import UTC, datetime
from secrets import token_urlsafe

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from sqlalchemy import delete, func, select

from app.class_names import format_class_name
from app.dependencies import DbSession, ProfessorUser
from app.errors import ErrorCode, api_error
from app.models import (
    ClassTrainingQuestionBank,
    Question,
    QuestionBank,
    QuizParticipant,
    QuizSession,
    QuizSessionQuestion,
    Student,
    StudentAccount,
    StudentClass,
)
from app.question_bank_summaries import load_question_bank_summaries
from app.routers.quizzes import (
    generate_join_code,
    participant_token_hash,
    student_state_response,
    training_profile_quiz,
)
from app.routers.student_auth import current_student
from app.schemas import (
    QuestionBankResponse,
    StudentQuizJoinResponse,
    TrainingHistoryItem,
    TrainingQuestionBankItem,
    TrainingQuestionBankSelection,
)
from app.services.grading import (
    training_result,
)
from app.services.question_draws import (
    MAX_TRAINING_QUESTIONS,
    draw_training_question_ids,
)
from app.services.session_lifecycle import (
    active_exam_bank_ids_for_class,
    discard_previous_training_sessions,
)

router = APIRouter(prefix="/api/quizzes", tags=["quizzes"])


@router.get(
    "/training/classes/{class_id}/question-banks",
    response_model=list[QuestionBankResponse],
)
def list_class_training_question_banks(
    class_id: int,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionBankResponse]:
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(status_code=404, detail="Classe introuvable")
    assignments = list(
        session.execute(
            select(
                ClassTrainingQuestionBank.question_bank_id,
                ClassTrainingQuestionBank.question_count,
            )
            .join(
                QuestionBank,
                QuestionBank.id == ClassTrainingQuestionBank.question_bank_id,
            )
            .where(
                ClassTrainingQuestionBank.class_id == class_id,
                QuestionBank.grade_level == student_class.grade_level,
            )
        )
    )
    responses = load_question_bank_summaries([row[0] for row in assignments], session)
    counts = dict(assignments)
    return [
        item.model_copy(update={"training_question_count": counts[item.id]})
        for item in responses
    ]


@router.put(
    "/training/classes/{class_id}/question-banks",
    response_model=list[QuestionBankResponse],
)
def update_class_training_question_banks(
    class_id: int,
    payload: TrainingQuestionBankSelection,
    professor: ProfessorUser,
    session: DbSession,
) -> list[QuestionBankResponse]:
    student_class = session.scalar(
        select(StudentClass).where(
            StudentClass.id == class_id,
            StudentClass.owner_id == professor.id,
        )
    )
    if student_class is None:
        raise HTTPException(status_code=404, detail="Classe introuvable")
    bank_ids = payload.question_bank_ids or [
        item.question_bank_id for item in payload.question_banks
    ]
    banks = list(
        session.scalars(
            select(QuestionBank).where(
                QuestionBank.id.in_(bank_ids),
                QuestionBank.owner_id == professor.id,
            )
        )
    )
    if len(banks) != len(bank_ids):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Une ou plusieurs banques de questions sont invalides",
        )
    if any(bank.grade_level != student_class.grade_level for bank in banks):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=(
                "Les banques d’entraînement doivent correspondre au niveau de la classe"
            ),
        )
    available = dict(
        session.execute(
            select(Question.question_bank_id, func.count(Question.id))
            .where(Question.question_bank_id.in_(bank_ids))
            .group_by(Question.question_bank_id)
        ).all()
    )
    configured_items = payload.question_banks or [
        TrainingQuestionBankItem(
            question_bank_id=bank_id,
            question_count=max(
                1, min(MAX_TRAINING_QUESTIONS, available.get(bank_id, 0))
            ),
        )
        for bank_id in bank_ids
    ]
    if payload.question_banks and any(
        item.question_count > available.get(item.question_bank_id, 0)
        for item in configured_items
    ):
        raise HTTPException(
            status_code=422,
            detail="Le nombre demandé dépasse les questions disponibles",
        )
    session.execute(
        delete(ClassTrainingQuestionBank).where(
            ClassTrainingQuestionBank.class_id == class_id
        )
    )
    session.add_all(
        ClassTrainingQuestionBank(
            class_id=class_id,
            question_bank_id=item.question_bank_id,
            question_count=item.question_count,
        )
        for item in configured_items
    )
    session.commit()
    responses = load_question_bank_summaries(bank_ids, session)
    counts = {item.question_bank_id: item.question_count for item in configured_items}
    return [
        item.model_copy(update={"training_question_count": counts[item.id]})
        for item in responses
    ]


@router.get("/training", response_model=list[QuestionBankResponse])
def list_student_training_question_banks(
    session: DbSession,
    student: StudentAccount = Depends(current_student),
) -> list[QuestionBankResponse]:
    memberships = list(
        session.scalars(select(Student).where(Student.account_id == student.id))
    )
    blocked_bank_ids = {
        bank_id
        for membership in memberships
        for bank_id in active_exam_bank_ids_for_class(membership.class_id, session)
    }
    bank_ids = list(
        session.scalars(
            select(ClassTrainingQuestionBank.question_bank_id)
            .join(Student, Student.class_id == ClassTrainingQuestionBank.class_id)
            .join(StudentClass, StudentClass.id == Student.class_id)
            .join(
                QuestionBank,
                QuestionBank.id == ClassTrainingQuestionBank.question_bank_id,
            )
            .where(
                Student.account_id == student.id,
                QuestionBank.grade_level == StudentClass.grade_level,
                ~ClassTrainingQuestionBank.question_bank_id.in_(blocked_bank_ids),
            )
        )
    )
    return load_question_bank_summaries(bank_ids, session)


@router.get(
    "/training/{question_bank_id}/history",
    response_model=list[TrainingHistoryItem],
)
def list_student_training_history(
    question_bank_id: int,
    session: DbSession,
    student: StudentAccount = Depends(current_student),
) -> list[TrainingHistoryItem]:
    membership = session.scalar(select(Student).where(Student.account_id == student.id))
    if membership is None:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                ErrorCode.TRAINING_CLASS_REQUIRED,
                "L’élève doit être affecté à une classe",
            ),
        )
    rows = list(
        session.execute(
            select(QuizSession, QuizParticipant)
            .join(
                QuizParticipant,
                QuizParticipant.session_id == QuizSession.id,
            )
            .where(
                QuizSession.training_question_bank_id == question_bank_id,
                QuizSession.status == "finished",
                QuizParticipant.student_id == membership.id,
                QuizSession.started_at.is_not(None),
            )
            .order_by(QuizSession.started_at, QuizSession.id)
        )
    )
    return [
        TrainingHistoryItem(
            session_id=quiz_session.id,
            question_bank_id=question_bank_id,
            started_at=quiz_session.started_at,
            score=score,
            maximum_score=maximum,
            pending_manual_review_count=pending,
        )
        for quiz_session, participant in rows
        for score, maximum, pending in [
            training_result(quiz_session, participant, session)
        ]
    ]


@router.post(
    "/training/{question_bank_id}/start",
    response_model=StudentQuizJoinResponse,
    status_code=status.HTTP_201_CREATED,
)
def start_training_quiz(
    question_bank_id: int,
    session: DbSession,
    student: StudentAccount = Depends(current_student),
) -> StudentQuizJoinResponse:
    membership = session.execute(
        select(Student, StudentClass)
        .join(StudentClass, StudentClass.id == Student.class_id)
        .where(Student.account_id == student.id)
    ).first()
    if membership is None:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                ErrorCode.TRAINING_CLASS_REQUIRED,
                "L’élève doit être affecté à une classe",
            ),
        )
    class_student, student_class = membership
    if question_bank_id in active_exam_bank_ids_for_class(student_class.id, session):
        raise HTTPException(
            status_code=404,
            detail=api_error(ErrorCode.TRAINING_NOT_FOUND, "Entraînement introuvable"),
        )
    assigned = session.execute(
        select(QuestionBank, ClassTrainingQuestionBank.question_count)
        .join(
            ClassTrainingQuestionBank,
            ClassTrainingQuestionBank.question_bank_id == QuestionBank.id,
        )
        .where(
            QuestionBank.id == question_bank_id,
            QuestionBank.owner_id == student.owner_id,
            QuestionBank.grade_level == student_class.grade_level,
            ClassTrainingQuestionBank.class_id == student_class.id,
        )
    ).first()
    if assigned is None:
        raise HTTPException(
            status_code=404,
            detail=api_error(ErrorCode.TRAINING_NOT_FOUND, "Entraînement introuvable"),
        )
    bank, configured_count = assigned
    question_ids = draw_training_question_ids(bank.id, session)[:configured_count]
    if not question_ids:
        raise HTTPException(
            status_code=409,
            detail=api_error(
                ErrorCode.TRAINING_BANK_EMPTY,
                "Cette banque ne contient encore aucune question",
            ),
        )
    quiz = training_profile_quiz(student.owner_id, session)
    discard_previous_training_sessions(student, class_student, session)
    now = datetime.now(UTC)
    quiz_session = QuizSession(
        quiz_id=quiz.id,
        quiz_title=bank.chapter,
        source_language=quiz.source_language,
        duration_seconds=28800,
        allow_previous_questions=False,
        allow_answer_review=False,
        allow_negative_points=False,
        same_questions_for_all=False,
        class_id=student_class.id,
        class_name=format_class_name(student_class.grade_level, student_class.name),
        join_code=generate_join_code(session),
        status="in_progress",
        started_at=now,
        training_question_bank_id=bank.id,
    )
    session.add(quiz_session)
    session.flush()
    session.add_all(
        QuizSessionQuestion(
            session_id=quiz_session.id,
            question_id=question_id,
            position=position,
        )
        for position, question_id in enumerate(question_ids)
    )
    participant_token = token_urlsafe(32)
    participant = QuizParticipant(
        session_id=quiz_session.id,
        student_id=class_student.id,
        student_identifier=student.identifier,
        student_display_name=student.display_name,
        access_token_hash=participant_token_hash(participant_token),
        current_position=0,
    )
    session.add(participant)
    session.commit()
    state = student_state_response(quiz_session, quiz, participant, session)
    return StudentQuizJoinResponse(
        **state.model_dump(),
        participant_token=participant_token,
    )

"""Request schemas reject invalid input before any route runs."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas import (
    GradeLevelCreate,
    ProblemReportCreate,
    QuestionBankCreate,
    QuestionChoiceCreate,
    QuestionCreate,
    QuizCreate,
    StudentAccountCreate,
    StudentAccountUpdate,
    StudentClassCreate,
    TrainingQuestionBankSelection,
)


def valid_question(**overrides: Any) -> dict[str, Any]:
    return {
        "prompt": "Pick one",
        "difficulty": "easy",
        "answer_mode": "single",
        "choices": [
            {"label": "Right", "is_correct": True},
            {"label": "Wrong", "is_correct": False},
        ],
        **overrides,
    }


def counts(easy: int) -> dict[str, int]:
    return {
        "easy_question_count": easy,
        "medium_question_count": 0,
        "hard_question_count": 0,
    }


def written_question(**overrides: Any) -> dict[str, Any]:
    return valid_question(
        **{
            "answer_mode": "written",
            "choices": [{"label": "Answer", "is_correct": True}],
            **overrides,
        }
    )


@pytest.mark.parametrize(
    ("model", "payload", "message"),
    [
        (ProblemReportCreate, {"message": "  a    ", "page_path": "/"}, "5 car"),
        (GradeLevelCreate, {"name": "   "}, "niveau"),
        (StudentAccountCreate, {"first_name": " ", "last_name": "B"}, "nom"),
        (
            StudentAccountUpdate,
            {"identifier": "pupil", "display_name": "  "},
            "nom",
        ),
        (StudentClassCreate, {"name": " ", "grade_level": "5e"}, "vide"),
        (QuestionBankCreate, {"grade_level": "5e", "chapter": "  "}, "vide"),
        (
            TrainingQuestionBankSelection,
            {
                "question_banks": [
                    {"question_bank_id": 1, "question_count": 1},
                    {"question_bank_id": 1, "question_count": 2},
                ]
            },
            "une fois",
        ),
        (QuestionChoiceCreate, {"label": "A", "code_language": "python"}, "ensemble"),
        (QuestionCreate, valid_question(prompt="  "), "vide"),
        (
            QuestionCreate,
            valid_question(choices=[{"label": "Only", "is_correct": True}]),
            "deux propositions",
        ),
        (
            QuestionCreate,
            written_question(
                choices=[
                    {"label": "A", "is_correct": True},
                    {"label": "B", "is_correct": False},
                ]
            ),
            "réponse attendue",
        ),
        (
            QuestionCreate,
            written_question(answer_mode_disclosed=False),
            "masqué",
        ),
        (QuestionCreate, valid_question(response_language="python"), "langage"),
        (QuestionCreate, valid_question(allow_code_execution=True), "exécution"),
        (
            QuestionCreate,
            written_question(allow_code_execution=True, response_language="sql"),
            "format Python",
        ),
        (
            QuestionCreate,
            valid_question(
                choices=[
                    {"label": "A", "is_correct": False},
                    {"label": "B", "is_correct": False},
                ]
            ),
            "au moins une bonne",
        ),
        (
            QuestionCreate,
            valid_question(
                choices=[
                    {"label": "A", "is_correct": True},
                    {"label": "B", "is_correct": True},
                ]
            ),
            "seule bonne",
        ),
        (QuestionCreate, valid_question(code_content="print(1)"), "ensemble"),
        (
            QuizCreate,
            {"title": "   ", "question_bank_ids": [1], **counts(1)},
            "titre",
        ),
        (
            QuizCreate,
            {"title": "Quiz", "question_bank_ids": [1], **counts(0)},
            "au moins une question",
        ),
        (
            QuizCreate,
            {
                "title": "Quiz",
                "question_bank_ids": [1],
                "easy_question_count": 100,
                "medium_question_count": 100,
                "hard_question_count": 1,
            },
            "plus de 200",
        ),
        (
            QuizCreate,
            {"title": "Quiz", "question_bank_ids": [1, 1], **counts(1)},
            "une fois",
        ),
    ],
)
def test_schemas_reject_invalid_input(model, payload, message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        model.model_validate(payload)


def test_questions_accept_a_python_code_execution_answer() -> None:
    question = QuestionCreate.model_validate(
        written_question(
            allow_code_execution=True,
            response_language="python",
            code_language="python",
            code_content="print(1)\r\n",
        )
    )
    assert question.code_content == "print(1)\n"
    assert (
        StudentAccountUpdate(
            identifier="pupil", display_name="Pupil", password=None
        ).password
        is None
    )
    with pytest.raises(ValidationError):
        TrainingQuestionBankSelection.model_validate({"question_bank_ids": [1, 2]})

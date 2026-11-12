"""The OpenAPI schema declares the responses the interface relies on."""

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from app import schemas
from app.routers import makeup

CODE_LANGUAGES = [
    "javascript",
    "typescript",
    "python",
    "java",
    "csharp",
    "cpp",
    "markup",
    "css",
    "sql",
    "bash",
    "json",
]


def enum_of(model: type[BaseModel], field: str) -> list[str]:
    """The values of a `Literal[...] | None` field, as the schema states them."""
    properties = model.model_json_schema(mode="serialization")["properties"]
    (choice,) = [
        item for item in properties[field]["anyOf"] if item.get("type") != "null"
    ]
    values: list[str] = choice["enum"]
    return values


def test_cancelling_a_makeup_session_is_declared_as_204() -> None:
    app = FastAPI()
    app.include_router(makeup.router)
    document: dict[str, Any] = app.openapi()
    responses = document["paths"]["/api/quizzes/makeup/sessions/{session_id}/{action}"][
        "post"
    ]["responses"]

    assert "204" in responses
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MakeupSessionResponse"
    }


def test_code_languages_are_the_request_vocabulary() -> None:
    fields: dict[type[BaseModel], list[str]] = {
        schemas.QuestionChoiceResponse: ["code_language"],
        schemas.QuestionContentResponse: ["code_language", "response_language"],
        schemas.StudentQuizChoiceResponse: ["code_language"],
        schemas.QuizAnswerReview: ["code_language", "response_language"],
        schemas.StudentQuizHistoryAnswer: ["code_language", "response_language"],
    }

    for model, names in fields.items():
        for name in names:
            assert enum_of(model, name) == CODE_LANGUAGES, f"{model.__name__}.{name}"


def test_last_violation_type_lists_every_recorded_alert() -> None:
    reported = schemas.StudentQuizViolation.model_json_schema()["properties"][
        "event_type"
    ]["enum"]

    assert enum_of(schemas.QuizParticipantResponse, "last_violation_type") == [
        *reported,
        "session_resumed",
    ]

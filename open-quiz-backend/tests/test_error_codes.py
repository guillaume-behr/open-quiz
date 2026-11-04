"""Every API error carries a stable code the interface can translate."""

import ast
from pathlib import Path

from fastapi import HTTPException

from app.errors import ApiError, ErrorCode, api_error

BACKEND = Path(__file__).resolve().parents[1]


def error_calls(name: str) -> list[tuple[str, str, ast.Call]]:
    found = []
    for path in [*sorted((BACKEND / "app").rglob("*.py")), BACKEND / "main.py"]:
        relative = path.relative_to(BACKEND).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        functions = (
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
        )
        found.extend(
            (relative, function.name, node)
            for function in functions
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == name
        )
    return found


def test_every_error_is_raised_with_a_code() -> None:
    """ApiError always carries a code: no route raises a bare HTTPException."""
    uncoded = [
        f"{path}:{call.lineno} in {function}"
        for path, function, call in error_calls("HTTPException")
    ]
    assert uncoded == []


def test_the_scan_sees_the_routers() -> None:
    assert len(error_calls("ApiError")) > 100


def test_an_api_error_renders_its_code_and_message() -> None:
    error = ApiError(404, ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable")
    assert isinstance(error, HTTPException)
    assert error.status_code == 404
    assert error.detail == api_error(ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable")


def test_an_error_pairs_its_code_with_a_message() -> None:
    assert api_error(ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable") == {
        "code": "QUIZ_NOT_FOUND",
        "message": "Quiz introuvable",
    }

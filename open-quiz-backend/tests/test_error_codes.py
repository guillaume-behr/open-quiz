"""Every API error carries a stable code the interface can translate."""

import ast
from pathlib import Path

from app.errors import ErrorCode, api_error

BACKEND = Path(__file__).resolve().parents[1]

# An unknown makeup action answers like an unknown route: a bare 404.
BARE_ERRORS = {("app/routers/makeup.py", "control_makeup_session")}


def http_exceptions() -> list[tuple[str, str, ast.Call]]:
    found = []
    for path in [*sorted((BACKEND / "app").rglob("*.py")), BACKEND / "main.py"]:
        relative = path.relative_to(BACKEND).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in ast.walk(tree):
            if not isinstance(function, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for node in ast.walk(function):
                if isinstance(node, ast.Call) and (
                    getattr(node.func, "id", None) == "HTTPException"
                ):
                    found.append((relative, function.name, node))
    return found


def test_every_http_exception_answers_with_a_code() -> None:
    uncoded = []
    for path, function, call in http_exceptions():
        detail = next((k.value for k in call.keywords if k.arg == "detail"), None)
        coded = (
            isinstance(detail, ast.Call)
            and getattr(detail.func, "id", None) == "api_error"
        )
        if not coded and (path, function) not in BARE_ERRORS:
            uncoded.append(f"{path}:{call.lineno} in {function}")
    assert uncoded == []


def test_the_scan_sees_the_routers() -> None:
    assert len(http_exceptions()) > 100


def test_an_error_pairs_its_code_with_a_message() -> None:
    assert api_error(ErrorCode.QUIZ_NOT_FOUND, "Quiz introuvable") == {
        "code": "QUIZ_NOT_FOUND",
        "message": "Quiz introuvable",
    }

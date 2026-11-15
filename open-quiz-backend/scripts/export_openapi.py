"""Write the API's OpenAPI schema, from which the frontend builds its types.

    uv run python -m scripts.export_openapi          # rewrite the file
    uv run python -m scripts.export_openapi --check  # fail if it is stale

The frontend then regenerates src/api/openapi.ts with
``pnpm generate:api-types``. tests/test_scripts.py fails while the committed
schema differs from the routes.
"""

import json
import sys
from argparse import ArgumentParser
from pathlib import Path

from fastapi import FastAPI

from app.application import include_routers

SCHEMA_FILE = (
    Path(__file__).resolve().parents[2]
    / "open-quiz-frontend"
    / "src"
    / "api"
    / "openapi.json"
)


def openapi_schema() -> str:
    """The schema of every route, as the file holds it."""
    # A fixed version rather than the release's, so that a release leaves the
    # file alone.
    app = FastAPI(title="Open Quiz API", version="current")
    include_routers(app)
    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main(arguments: list[str] | None = None) -> int:
    parser = ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the file differs from the routes, instead of writing it.",
    )
    check = parser.parse_args(arguments).check
    schema = openapi_schema()
    current = SCHEMA_FILE.read_text(encoding="utf-8") if SCHEMA_FILE.exists() else ""
    if not check:
        SCHEMA_FILE.write_text(schema, encoding="utf-8")
        return 0
    if current != schema:
        print(
            f"{SCHEMA_FILE} is out of date: run "
            "`uv run python -m scripts.export_openapi`.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

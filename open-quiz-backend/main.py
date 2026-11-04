"""Entry point served by Uvicorn: ``fastapi dev main.py`` or ``main:app``."""

from app.application import create_app

app = create_app()

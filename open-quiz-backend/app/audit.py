import json
import logging

logger = logging.getLogger("open_quiz.audit")
logger.setLevel(logging.INFO)


def audit_event(event: str, **details: object) -> None:
    logger.info(json.dumps({"event": event, **details}, separators=(",", ":")))

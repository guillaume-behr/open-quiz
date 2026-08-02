import json
import logging
import sys
from datetime import UTC, datetime

logger = logging.getLogger("open_quiz.audit")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(logging.INFO)
    logger.addHandler(handler)
logger.propagate = False


def audit_event(event: str, **details: object) -> None:
    logger.info(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "event": event,
                **details,
            },
            separators=(",", ":"),
        )
    )

import json
import logging
from datetime import UTC, datetime

logger = logging.getLogger("open_quiz.audit")
logger.setLevel(logging.INFO)


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

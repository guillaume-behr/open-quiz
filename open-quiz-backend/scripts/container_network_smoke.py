import asyncio
import json
from urllib.request import Request, urlopen

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

FRONTEND_URL = "http://open-quiz-frontend:8080"
FRONTEND_ORIGIN = "https://quiz.example.com"


def check_http_proxy() -> None:
    request = Request(f"{FRONTEND_URL}/api/health")  # noqa: S310 - fixed URL
    with urlopen(request, timeout=5) as response:  # noqa: S310 - fixed URL
        payload = json.load(response)
    if payload != {"status": "ok"}:
        raise RuntimeError(f"Unexpected health response: {payload!r}")


async def check_websocket_proxy() -> None:
    async with connect(
        "ws://open-quiz-frontend:8080/api/quizzes/live/teacher/sessions",
        origin=FRONTEND_ORIGIN,
        open_timeout=5,
        close_timeout=5,
    ) as websocket:
        await websocket.send(json.dumps({"token": "invalid-smoke-test-token"}))
        try:
            await websocket.recv()
        except ConnectionClosed as error:
            if error.code != 1008:
                raise RuntimeError(
                    f"Unexpected WebSocket close code: {error.code}"
                ) from error
            return
    raise RuntimeError("Invalid WebSocket credentials were not rejected")


def main() -> None:
    check_http_proxy()
    asyncio.run(check_websocket_proxy())


if __name__ == "__main__":
    main()

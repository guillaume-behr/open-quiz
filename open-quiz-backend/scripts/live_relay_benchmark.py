"""Measure how fast a publication reaches the sockets of another worker.

Run from open-quiz-backend with DATABASE_URL pointing at PostgreSQL:

    uv run python -m scripts.live_relay_benchmark --subscribers 140

One relay publishes as a first worker would; a second relay and its hub stand
for another worker holding the subscribers. Each round publishes one session
topic and records the time until every subscriber of that topic has woken.
"""

import argparse
import asyncio
import os
import statistics
from time import perf_counter

from app.database import postgres_url
from app.live_quiz import LiveQuizHub, quiz_session_topic
from app.live_relay import PostgresLiveRelay


async def one_round(
    hub: LiveQuizHub, publisher: PostgresLiveRelay, topic: str, sockets: int
) -> float:
    """Milliseconds from a publication until all of a topic's sockets woke."""
    woken = asyncio.Event()
    remaining = sockets
    readiness = [asyncio.Event() for _ in range(sockets)]

    async def subscriber(ready: asyncio.Event) -> None:
        nonlocal remaining
        async with hub.subscribe(topic) as updates:
            ready.set()
            await updates.get()
            remaining -= 1
            if remaining == 0:
                woken.set()

    tasks = [asyncio.create_task(subscriber(ready)) for ready in readiness]
    await asyncio.gather(*(ready.wait() for ready in readiness))
    started = perf_counter()
    await asyncio.to_thread(publisher.send, topic)
    await asyncio.wait_for(woken.wait(), timeout=5)
    elapsed = (perf_counter() - started) * 1000
    await asyncio.gather(*tasks)
    return elapsed


async def measure(subscribers: int, sessions: int, rounds: int) -> list[float]:
    conninfo = (
        postgres_url(os.environ["DATABASE_URL"])
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    receiving_hub = LiveQuizHub()
    publisher = PostgresLiveRelay(conninfo, lambda _: None)
    receiver = PostgresLiveRelay(conninfo, receiving_hub.publish_local)
    receiver.start()
    await asyncio.to_thread(receiver.listening.wait, 5)
    try:
        return [
            await one_round(
                receiving_hub,
                publisher,
                quiz_session_topic(round_number % sessions),
                subscribers // sessions,
            )
            for round_number in range(rounds)
        ]
    finally:
        publisher.stop()
        receiver.stop()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--subscribers", type=int, default=140)
    parser.add_argument("--sessions", type=int, default=4)
    parser.add_argument("--rounds", type=int, default=200)
    arguments = parser.parse_args(argv)
    latencies = asyncio.run(
        measure(arguments.subscribers, arguments.sessions, arguments.rounds)
    )
    ordered = sorted(latencies)
    print(
        f"{arguments.rounds} publications to {arguments.subscribers // arguments.sessions}"
        f" sockets each: median {statistics.median(ordered):.1f} ms,"
        f" p95 {ordered[int(len(ordered) * 0.95) - 1]:.1f} ms,"
        f" max {ordered[-1]:.1f} ms"
    )


if __name__ == "__main__":
    main()

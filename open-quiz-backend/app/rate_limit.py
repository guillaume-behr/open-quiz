from collections import deque
from threading import Lock
from time import monotonic


class LoginRateLimiter:
    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def retry_after(self, ip_address: str, username: str) -> int:
        now = monotonic()
        with self._lock:
            for key in self._keys(ip_address, username):
                attempts = self._attempts.get(key)
                if attempts is None:
                    continue
                self._discard_expired(attempts, now)
                if not attempts:
                    self._attempts.pop(key)
                    continue
                if len(attempts) >= self.limit:
                    return max(1, int(self.window_seconds - (now - attempts[0])))
        return 0

    def record_failure(self, ip_address: str, username: str) -> None:
        now = monotonic()
        with self._lock:
            for key in self._keys(ip_address, username):
                attempts = self._attempts.setdefault(key, deque())
                self._discard_expired(attempts, now)
                attempts.append(now)

    def clear(self, ip_address: str, username: str) -> None:
        with self._lock:
            for key in self._keys(ip_address, username):
                self._attempts.pop(key, None)

    def _discard_expired(self, attempts: deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()

    @staticmethod
    def _keys(ip_address: str, username: str) -> tuple[str, str]:
        return f"ip:{ip_address}", f"user:{username.casefold()}"

from fastapi import Request


def client_ip(request: Request) -> str:
    """Return a stable identifier when the ASGI client address is unavailable."""
    return request.client.host if request.client else "unknown"

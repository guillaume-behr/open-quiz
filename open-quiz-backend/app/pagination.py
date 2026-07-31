from fastapi import Response

DEFAULT_PAGE_SIZE = 8
MAX_PAGE_SIZE = 100


def set_pagination_headers(
    response: Response, *, page: int, page_size: int, total: int
) -> None:
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Count"] = str(total)

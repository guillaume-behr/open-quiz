from fastapi import Response

DEFAULT_PAGE_SIZE = 8
MAX_PAGE_SIZE = 100


def set_pagination_headers(
    response: Response, *, page: int, page_size: int, total: int
) -> None:
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Count"] = str(total)


LIKE_ESCAPE_CHARACTER = "\\"


def contains_pattern(search: str) -> str:
    """A LIKE pattern matching ``search`` literally anywhere in a value.

    Search boxes take plain text: an unescaped ``%`` or ``_`` would act as a
    wildcard, so looking for ``jean_d`` would also list ``jeanXd``. Use the
    result with ``escape=LIKE_ESCAPE_CHARACTER``.
    """
    escaped = (
        search.replace(LIKE_ESCAPE_CHARACTER, LIKE_ESCAPE_CHARACTER * 2)
        .replace("%", f"{LIKE_ESCAPE_CHARACTER}%")
        .replace("_", f"{LIKE_ESCAPE_CHARACTER}_")
    )
    return f"%{escaped}%"

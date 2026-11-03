from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import Depends, Query, Response
from sqlalchemy import ColumnElement, func, select, tuple_
from sqlalchemy.orm import Session

DEFAULT_PAGE_SIZE = 8
MAX_PAGE_SIZE = 100
# Bound the page number so the OFFSET of (page - 1) * page_size always fits a
# PostgreSQL bigint: an unbounded page overflowed it and failed with a 500.
# A million pages of the largest size is far past any real list.
MAX_PAGE = 1_000_000


@dataclass
class Pagination:
    """The page a list endpoint answers, and the headers that describe it."""

    page: int
    page_size: int
    response: Response

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size

    def set_total(self, total: int) -> None:
        set_pagination_headers(
            self.response, page=self.page, page_size=self.page_size, total=total
        )


def pagination(
    response: Response,
    page: Annotated[int, Query(ge=1, le=MAX_PAGE)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = DEFAULT_PAGE_SIZE,
) -> Pagination:
    return Pagination(page=page, page_size=page_size, response=response)


Paging = Annotated[Pagination, Depends(pagination)]


def set_pagination_headers(
    response: Response, *, page: int, page_size: int, total: int
) -> None:
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Count"] = str(total)


def focused_page(
    session: Session,
    model: Any,
    filters: list[ColumnElement[bool]],
    order: tuple[Any, ...],
    focus_id: int,
    page_size: int,
) -> int | None:
    """The page that holds ``focus_id`` in a list sorted by ``order``.

    ``order`` must end with the primary key, so that rows compare as they
    sort. Returns None when the row is not in the filtered list, letting the
    caller keep the requested page. A client uses this after creating an
    item, to show the page that holds it without loading every page.
    """
    target = session.execute(
        select(*order).where(*filters, model.id == focus_id)
    ).one_or_none()
    if target is None:
        return None
    preceding = session.scalar(
        select(func.count())
        .select_from(model)
        .where(*filters, tuple_(*order) < tuple_(*target))
    )
    return (preceding or 0) // page_size + 1


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

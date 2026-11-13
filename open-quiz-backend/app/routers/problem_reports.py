from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request, Response, status
from sqlalchemy import ColumnElement, func, select

from app.core.audit import audit_event
from app.core.dependencies import AdminUser, DbSession
from app.core.errors import ApiError, ErrorCode
from app.core.pagination import (
    Paging,
)
from app.models import ProblemReport
from app.schemas import ProblemReportCreate, ProblemReportResponse

router = APIRouter(prefix="/api/problem-reports", tags=["problem reports"])


def retained_report(request: Request) -> ColumnElement[bool]:
    """Whether a report is within its retention.

    The hourly maintenance deletes expired reports; until it runs, they are
    already hidden.
    """
    cutoff = datetime.now(UTC) - timedelta(
        days=request.app.state.settings.problem_report_retention_days
    )
    return ProblemReport.created_at > cutoff


@router.post(
    "",
    response_model=ProblemReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_problem_report(
    payload: ProblemReportCreate,
    request: Request,
    session: DbSession,
) -> ProblemReport:
    # Anonymous endpoint: abuse is contained by an instance-wide budget so that
    # no client identifier (especially an IP address) is ever used as a quota
    # identity.
    retry_after = request.app.state.problem_report_rate_limiter.reserve(
        "problem-report:instance"
    )
    if retry_after:
        raise ApiError(
            status.HTTP_429_TOO_MANY_REQUESTS,
            ErrorCode.PROBLEM_REPORT_RATE_LIMITED,
            "Trop de signalements envoyés. Réessayez plus tard.",
            headers={"Retry-After": str(retry_after)},
        )
    report = ProblemReport(
        message=payload.message,
        page_path=payload.page_path,
    )
    session.add(report)
    session.commit()
    session.refresh(report)
    audit_event("problem_report.created", report_id=report.id)
    return report


@router.get("", response_model=list[ProblemReportResponse])
def list_problem_reports(
    request: Request,
    _: AdminUser,
    session: DbSession,
    paging: Paging,
) -> list[ProblemReport]:
    retained = retained_report(request)
    total = (
        session.scalar(select(func.count()).select_from(ProblemReport).where(retained))
        or 0
    )
    paging.set_total(total)
    return list(
        session.scalars(
            select(ProblemReport)
            .where(retained)
            .order_by(ProblemReport.created_at.desc(), ProblemReport.id.desc())
            .offset(paging.offset)
            .limit(paging.page_size)
        )
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_problem_report(
    report_id: int,
    admin_user: AdminUser,
    session: DbSession,
) -> Response:
    report = session.get(ProblemReport, report_id)
    if report is None:
        raise ApiError(
            status.HTTP_404_NOT_FOUND,
            ErrorCode.PROBLEM_REPORT_NOT_FOUND,
            "Signalement introuvable",
        )
    session.delete(report)
    session.commit()
    audit_event(
        "problem_report.deleted",
        report_id=report_id,
        actor_id=admin_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import delete, select

from app.audit import audit_event
from app.dependencies import AdminUser, DbSession
from app.models import ProblemReport
from app.schemas import ProblemReportCreate, ProblemReportResponse

router = APIRouter(prefix="/api/problem-reports", tags=["problem reports"])


def purge_expired_reports(request: Request, session: DbSession) -> None:
    cutoff = datetime.now(UTC) - timedelta(
        days=request.app.state.settings.problem_report_retention_days
    )
    session.execute(delete(ProblemReport).where(ProblemReport.created_at <= cutoff))


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
    retry_after = request.app.state.problem_report_rate_limiter.reserve(
        session, "instance-wide"
    )
    if retry_after:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de signalements envoyés. Réessayez plus tard.",
            headers={"Retry-After": str(retry_after)},
        )
    purge_expired_reports(request, session)
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
) -> list[ProblemReport]:
    purge_expired_reports(request, session)
    session.commit()
    return list(
        session.scalars(select(ProblemReport).order_by(ProblemReport.created_at.desc()))
    )


@router.delete("/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_problem_report(
    report_id: int,
    request: Request,
    admin_user: AdminUser,
    session: DbSession,
) -> Response:
    report = session.get(ProblemReport, report_id)
    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Signalement introuvable",
        )
    session.delete(report)
    session.commit()
    audit_event(
        "problem_report.deleted",
        report_id=report_id,
        actor_id=admin_user.id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)

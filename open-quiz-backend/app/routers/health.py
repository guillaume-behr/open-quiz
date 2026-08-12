from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(request: Request) -> dict[str, str]:
    """Report whether the API and its database are ready."""
    try:
        with request.app.state.session_factory() as session:
            session.execute(text("SELECT 1"))
    except SQLAlchemyError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from error
    return {"status": "ok"}


@router.get("/public-information")
def public_information(request: Request) -> dict[str, object]:
    """Expose only the instance information required on public legal pages."""
    settings = request.app.state.settings
    return {
        "host": {
            "name": settings.legal_host_name,
            "address": settings.legal_host_address,
            "phone": settings.legal_host_phone,
        },
        "privacy": {
            "controller_name": settings.privacy_controller_name,
            "controller_contact": settings.privacy_controller_contact,
            "dpo_contact": settings.privacy_dpo_contact,
            "legal_basis": settings.privacy_legal_basis,
            "recipients": settings.privacy_recipients,
            "teacher_data_retention": (settings.privacy_teacher_data_retention),
            "student_data_retention": (settings.privacy_student_data_retention),
            "security_log_retention": (settings.privacy_security_log_retention),
            "quiz_result_retention_days": (settings.quiz_result_retention_days),
            "problem_report_retention_days": (settings.problem_report_retention_days),
        },
        "cookies": {
            "authentication_max_age_days": settings.refresh_token_days,
        },
        "accessibility": {
            "contact": settings.accessibility_contact,
            "scheme_url": settings.accessibility_scheme_url,
            "action_plan_url": settings.accessibility_action_plan_url,
        },
    }

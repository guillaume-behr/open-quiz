from secrets import choice
from string import digits

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Student, StudentAccount, StudentClass
from app.schemas import StudentAccountResponse

READABLE_CONSONANTS = "BCDFGHJKMNPRSTVWXYZ"
READABLE_VOWELS = "AEU"


def generated_student_password() -> str:
    # Pronounceable letters plus digits: 19^4 * 3^4 * 10^2 (~30 bits) while
    # staying easy for young students to copy.
    letters = "".join(
        choice(READABLE_CONSONANTS if index % 2 == 0 else READABLE_VOWELS)
        for index in range(8)
    )
    return f"{letters}{choice(digits)}{choice(digits)}"


def student_account_response(
    account: StudentAccount, session: Session
) -> StudentAccountResponse:
    membership = session.execute(
        select(Student.class_id, StudentClass.name, StudentClass.grade_level)
        .join(StudentClass, StudentClass.id == Student.class_id)
        .where(Student.account_id == account.id)
    ).first()
    return student_account_response_from_membership(
        account,
        (membership[0], membership[1], membership[2]) if membership else None,
    )


def student_account_response_from_membership(
    account: StudentAccount,
    membership: tuple[int, str, str] | None,
) -> StudentAccountResponse:
    return StudentAccountResponse(
        id=account.id,
        identifier=account.identifier,
        display_name=account.display_name,
        is_active=account.is_active,
        class_id=membership[0] if membership else None,
        class_name=membership[1] if membership else None,
        grade_level=membership[2] if membership else None,
        created_at=account.created_at,
    )


def owned_student_account(
    account_id: int, owner_id: int, session: Session
) -> StudentAccount:
    account = session.scalar(
        select(StudentAccount).where(
            StudentAccount.id == account_id,
            StudentAccount.owner_id == owner_id,
        )
    )
    if account is None:
        raise HTTPException(status_code=404, detail="Compte élève introuvable")
    return account

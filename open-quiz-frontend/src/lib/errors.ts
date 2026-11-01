import { ApiError } from "@/api/client"

// Every code the backend returns needs a key here: auth.py's auth_error()
// codes and the ErrorCode members of app/errors.py. scripts/check-error-codes.mjs
// fails `pnpm test` when one is missing.
export const API_ERROR_TRANSLATION_KEYS: Record<string, string> = {
    AUTH_ORIGIN_REJECTED: "auth-origin-rejected",
    AUTH_INVALID_CREDENTIALS: "student-login-error",
    AUTH_RATE_LIMITED: "auth-rate-limited",
    AUTH_PROFESSOR_ACCOUNT_REQUIRED: "professor-account-required",
    AUTH_ADMIN_ACCOUNT_REQUIRED: "admin-only",
    AUTH_2FA_CHALLENGE_INVALID: "two-factor-challenge-invalid",
    AUTH_2FA_RATE_LIMITED: "two-factor-rate-limited",
    AUTH_2FA_UNAVAILABLE: "two-factor-unavailable",
    AUTH_2FA_CODE_INVALID: "two-factor-code-invalid",
    AUTH_2FA_CODE_USED: "two-factor-code-used",
    QUIZ_RATE_LIMITED: "error-quiz-rate-limited",
    QUIZ_JOIN_REJECTED: "error-quiz-join-rejected",
    QUIZ_PARTICIPANT_TOKEN_MISSING: "error-quiz-session-expired",
    QUIZ_PARTICIPANT_TOKEN_INVALID: "error-quiz-session-expired",
    QUIZ_QUESTION_UNAVAILABLE: "error-quiz-question-unavailable",
    QUIZ_NO_CURRENT_QUESTION: "error-quiz-question-unavailable",
    QUIZ_NOT_ACCEPTING_ANSWERS: "error-quiz-not-accepting-answers",
    QUIZ_STUDENT_REMOVED: "error-quiz-student-removed",
    TRAINING_BLOCKED_BY_EXAM: "error-training-blocked-by-exam",
    ANSWER_WRITTEN_REQUIRED: "error-answer-written-required",
    ANSWER_CHOICE_REQUIRED: "error-answer-choice-required",
    ANSWER_MODE_MISMATCH: "error-answer-invalid",
    ANSWER_CHOICE_INVALID: "error-answer-invalid",
    QUIZ_ANSWERS_INCOMPLETE: "error-quiz-answers-incomplete",
    QUIZ_REVIEW_UNAVAILABLE: "error-quiz-review-unavailable",
    QUIZ_PREVIOUS_QUESTION_LOCKED: "error-quiz-previous-question-locked",
    TRAINING_CLASS_REQUIRED: "error-training-class-required",
    TRAINING_NOT_FOUND: "error-training-not-found",
    TRAINING_BANK_EMPTY: "error-training-bank-empty",
    MAKEUP_JOIN_REJECTED: "error-makeup-join-rejected",
    MAKEUP_SELECTION_CLOSED: "error-makeup-selection-closed",
    MAKEUP_SELECTION_INVALID: "error-makeup-selection-invalid",
    STUDENT_SESSION_INVALID: "error-student-session-expired",
    CLASS_NOT_FOUND: "error-class-not-found",
    CLASS_NAME_TAKEN: "error-class-name-taken",
    CLASS_USED_BY_WAITING_ROOM: "error-class-used-by-waiting-room",
    CLASS_USED_BY_MAKEUP: "error-class-used-by-makeup",
    CLASS_HAS_ACTIVE_SESSION: "error-class-has-active-session",
    CLASS_ASSIGNMENT_NOT_FOUND: "error-class-assignment-not-found",
    CLASS_IMPORT_DUPLICATES: "error-class-import-duplicates",
    CLASS_IMPORT_GRADE_LEVEL_INVALID: "error-class-import-grade-level-invalid",
    CLASS_IMPORT_CONFLICT: "error-class-import-conflict",
    STUDENT_IDENTIFIER_TAKEN: "error-student-identifier-taken",
    STUDENT_TRANSFER_DURING_SESSION: "error-student-transfer-during-session",
    STUDENT_ACCOUNT_NOT_FOUND: "error-student-account-not-found",
    STUDENT_ACCOUNT_IN_ACTIVE_SESSION:
        "error-student-account-in-active-session",
    STUDENT_FILTERS_INVALID: "error-student-filters-invalid",
    GRADE_LEVEL_NOT_FOUND: "error-grade-level-not-found",
    GRADE_LEVEL_IN_USE: "error-grade-level-in-use",
}

export function errorMessage(error: unknown, fallback: string): string {
    // Server error details without a code are not localized: prefer the
    // translated fallback for API errors. Deliberately thrown local errors
    // (already translated) are shown as-is.
    if (error instanceof ApiError) return fallback
    return error instanceof Error ? error.message : fallback
}

export function localizedErrorMessage(
    error: unknown,
    translate: (key: string) => string,
    fallback: string
): string {
    if (!(error instanceof ApiError) || !error.code) {
        return errorMessage(error, fallback)
    }
    const translationKey = API_ERROR_TRANSLATION_KEYS[error.code]
    return translationKey ? translate(translationKey) : fallback
}

// For screens that only ever show their own translated fallback: a known API
// code gets its specific message, anything else (network failure, timeout,
// unknown code) keeps the fallback rather than an untranslated message.
export function apiErrorMessage(
    error: unknown,
    translate: (key: string) => string,
    fallback: string
): string {
    const translationKey =
        error instanceof ApiError && error.code
            ? API_ERROR_TRANSLATION_KEYS[error.code]
            : undefined
    return translationKey ? translate(translationKey) : fallback
}

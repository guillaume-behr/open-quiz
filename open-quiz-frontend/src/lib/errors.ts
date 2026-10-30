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

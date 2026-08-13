import { ApiError } from "@/api/client"

const AUTH_ERROR_TRANSLATION_KEYS: Record<string, string> = {
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
}

export function errorMessage(error: unknown, fallback: string): string {
    // Server error details are not localized: prefer the translated fallback
    // for API errors. Deliberately thrown local errors (already translated)
    // are shown as-is.
    if (error instanceof ApiError) return fallback
    return error instanceof Error ? error.message : fallback
}

export function localizedAuthErrorMessage(
    error: unknown,
    translate: (key: string) => string,
    fallback: string
): string {
    if (!(error instanceof ApiError) || !error.code) {
        return errorMessage(error, fallback)
    }
    const translationKey = AUTH_ERROR_TRANSLATION_KEYS[error.code]
    return translationKey ? translate(translationKey) : fallback
}

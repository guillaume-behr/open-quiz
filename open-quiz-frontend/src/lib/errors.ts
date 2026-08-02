import { ApiError } from "@/api/client"

export function errorMessage(error: unknown, fallback: string): string {
    // Server error details are not localized: prefer the translated fallback
    // for API errors. Deliberately thrown local errors (already translated)
    // are shown as-is.
    if (error instanceof ApiError) return fallback
    return error instanceof Error ? error.message : fallback
}

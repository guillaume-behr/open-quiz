import type { QuizSession } from "@/api/types"

type SessionStatus = QuizSession["status"]

const ACTIVE_SESSION_STATUSES = new Set<SessionStatus>([
    "waiting",
    "in_progress",
    "paused",
])

export function isActiveSessionStatus(
    status: SessionStatus | null | undefined
): boolean {
    return (
        status !== null &&
        status !== undefined &&
        ACTIVE_SESSION_STATUSES.has(status)
    )
}

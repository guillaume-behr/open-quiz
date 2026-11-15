const ACTIVE_SESSION_STATUSES = new Set<string>([
    "waiting",
    "in_progress",
    "paused",
])

export function isActiveSessionStatus(
    status: string | null | undefined
): boolean {
    return (
        status !== null &&
        status !== undefined &&
        ACTIVE_SESSION_STATUSES.has(status)
    )
}

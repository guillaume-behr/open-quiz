export function resultStart(result: {
    started_at: string | null
    created_at: string
}): Date {
    return new Date(result.started_at ?? result.created_at)
}

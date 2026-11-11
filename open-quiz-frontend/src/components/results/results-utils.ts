export function resultStart(result: {
    started_at: string | null
    created_at: string
}): Date {
    return new Date(result.started_at ?? result.created_at)
}

export const DAYS_PER_WEEK = 7

/** Monday, midnight local time, of the week holding `date`. */
export function startOfWeek(date: Date): Date {
    const start = new Date(date)
    const mondayOffset = (start.getDay() + 6) % DAYS_PER_WEEK
    start.setDate(start.getDate() - mondayOffset)
    start.setHours(0, 0, 0, 0)
    return start
}

export function addDays(date: Date, amount: number): Date {
    const next = new Date(date)
    next.setDate(next.getDate() + amount)
    return next
}

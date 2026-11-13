/** The server's time at one instant of the monotonic clock. */
export type ServerClockAnchor = {
    serverTime: number
    monotonicTime: number
}

/**
 * Anchor a server timestamp to `performance.now()`, at the moment it arrives.
 *
 * Elapsed time is then measured on the monotonic clock, which a change of
 * the computer's date or time does not move.
 */
export function serverClockAnchor(
    serverNow: string | null | undefined
): ServerClockAnchor | null {
    if (!serverNow) return null
    const serverTime = Date.parse(serverNow)
    if (Number.isNaN(serverTime)) return null
    return { serverTime, monotonicTime: performance.now() }
}

/** The server's current time, or the client's when no anchor is known. */
function serverTimeNow(anchor: ServerClockAnchor | null): number {
    if (!anchor) return Date.now()
    return anchor.serverTime + (performance.now() - anchor.monotonicTime)
}

/** Whole seconds left until `endsAt`, on the server's clock. */
export function secondsLeft(
    endsAt: string,
    anchor: ServerClockAnchor | null
): number {
    return Math.max(
        0,
        Math.floor((Date.parse(endsAt) - serverTimeNow(anchor)) / 1000)
    )
}

// Minutes left at which a screen reader hears how much time remains.
const TIMER_ANNOUNCEMENT_MINUTES = [10, 5, 1] as const

/**
 * The threshold the countdown just crossed, if any.
 *
 * Only a crossing counts: a page opened with less time already left
 * announces nothing until the next threshold.
 */
export function crossedAnnouncement(
    previousSeconds: number | null,
    seconds: number
): number | undefined {
    if (previousSeconds === null) return undefined
    return TIMER_ANNOUNCEMENT_MINUTES.find(
        (minutes) => previousSeconds > minutes * 60 && seconds <= minutes * 60
    )
}

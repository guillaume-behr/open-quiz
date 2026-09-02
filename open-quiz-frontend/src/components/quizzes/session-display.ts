import type { MakeupSession, QuizSession } from "@/api/types"

/**
 * The projection tab is fed by the dashboard tab, never by the API.
 *
 * A second authenticated tab would rotate the shared refresh token behind the
 * first one and log the teacher out of both, so the enlarged view stays a
 * passive mirror: the supervising tab publishes what it already received on
 * its live socket, through a broadcast channel with a stored last value so a
 * reload has something to render immediately.
 */
export type SessionDisplayPayload = {
    sessionKey: string
    title: string
    className: string
    joinCode: string
    status: QuizSession["status"]
    endsAt: string | null
    participantCount: number
    finishedCount: number
    updatedAt: number
}

const CHANNEL_NAME = "open-quiz-session-display"
const STORAGE_PREFIX = "open-quiz-session-display:"
const MAXIMUM_AGE_MS = 12 * 60 * 60 * 1000
const SESSION_KEY_PATTERN = /^(?:quiz|makeup)-\d+$/

export function sessionDisplayKey(
    session: QuizSession | MakeupSession
): string {
    return `${"quiz_id" in session ? "quiz" : "makeup"}-${session.id}`
}

export function sessionDisplayPath(sessionKey: string): string {
    return `/teacher/session-display/${sessionKey}`
}

export function isSessionDisplayKey(
    value: string | undefined
): value is string {
    return typeof value === "string" && SESSION_KEY_PATTERN.test(value)
}

function storageKey(sessionKey: string): string {
    return `${STORAGE_PREFIX}${sessionKey}`
}

function parsePayload(raw: string | null): SessionDisplayPayload | null {
    if (!raw) return null
    try {
        const payload = JSON.parse(raw) as SessionDisplayPayload
        if (!isSessionDisplayKey(payload.sessionKey)) return null
        if (Date.now() - payload.updatedAt > MAXIMUM_AGE_MS) return null
        return payload
    } catch {
        return null
    }
}

export function publishSessionDisplay(payload: SessionDisplayPayload): void {
    const serialized = JSON.stringify(payload)
    try {
        localStorage.setItem(storageKey(payload.sessionKey), serialized)
    } catch {
        // A projection without storage still receives live broadcasts.
    }
    try {
        const channel = new BroadcastChannel(CHANNEL_NAME)
        channel.postMessage(payload)
        channel.close()
    } catch {
        // Browsers without broadcast channels fall back to storage events.
    }
}

export function readSessionDisplay(
    sessionKey: string
): SessionDisplayPayload | null {
    try {
        return parsePayload(localStorage.getItem(storageKey(sessionKey)))
    } catch {
        return null
    }
}

export function subscribeSessionDisplay(
    sessionKey: string,
    onPayload: (payload: SessionDisplayPayload) => void
): () => void {
    let channel: BroadcastChannel | null = null
    const handleMessage = (event: MessageEvent<SessionDisplayPayload>) => {
        const payload = event.data
        if (payload?.sessionKey === sessionKey) onPayload(payload)
    }
    const handleStorage = (event: StorageEvent) => {
        if (event.key !== storageKey(sessionKey)) return
        const payload = parsePayload(event.newValue)
        if (payload) onPayload(payload)
    }
    try {
        channel = new BroadcastChannel(CHANNEL_NAME)
        channel.addEventListener("message", handleMessage)
    } catch {
        channel = null
    }
    window.addEventListener("storage", handleStorage)
    return () => {
        channel?.removeEventListener("message", handleMessage)
        channel?.close()
        window.removeEventListener("storage", handleStorage)
    }
}

export function sessionDisplayPayload(
    session: QuizSession | MakeupSession,
    title: string
): SessionDisplayPayload {
    const participants = session.participants ?? []
    return {
        sessionKey: sessionDisplayKey(session),
        title,
        className: session.class_name,
        joinCode: session.join_code,
        status: session.status,
        endsAt: "ends_at" in session ? session.ends_at : null,
        participantCount: session.participant_count,
        finishedCount: participants.filter(
            (participant) => participant.has_finished
        ).length,
        updatedAt: Date.now(),
    }
}

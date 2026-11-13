import * as v from "valibot"

import { apiWebSocketUrl } from "@/api/client"
import { LiveMessageSchema } from "@/api/schemas"

type LiveSocketOptions<T> = {
    path: string
    getToken: (forceRefresh: boolean) => Promise<string | null>
    /**
     * Checks each update before onData sees it; an update that fails is
     * ignored. Without it, the feed's data is trusted as `T`.
     */
    schema?: v.GenericSchema<unknown, T>
    onData: (data: T) => void
    onDeleted?: () => void
    onUnavailable: () => void
    /** Told when updates flow again, and when they stop until a reconnect. */
    onConnectionChange?: (state: LiveConnectionState) => void
}

export type LiveConnectionState = "connected" | "reconnecting"

const MAX_RECONNECT_DELAY_MS = 10_000
const CONNECTION_TIMEOUT_MS = 10_000
const RECONNECT_JITTER = 0.25
/** The server sends a ping at least this often (`LiveHeartbeat`). */
const SERVER_HEARTBEAT_MS = 25_000
/**
 * Silence after which an open socket is presumed dead: a half-open
 * connection (sleep and wake, a network change, a proxy dropping the stream)
 * stays OPEN and never reports closing. Two heartbeats plus a margin.
 */
export const LIVENESS_TIMEOUT_MS = 60_000
/**
 * When the tab comes back or the network returns, a connection silent for
 * longer than a heartbeat (plus a margin for delivery) is replaced at once:
 * background tabs throttle timers, so the watchdog may not have run yet.
 */
const STALE_AFTER_MS = SERVER_HEARTBEAT_MS + 5_000

/**
 * A malformed update is dropped: the screen keeps its last good state, and
 * the next update (they are full states, not changes) brings it up to date.
 */
function ignoreMalformedUpdate(
    path: string,
    issues: [v.BaseIssue<unknown>, ...v.BaseIssue<unknown>[]]
) {
    console.warn("Ignored a malformed live update", path, v.flatten(issues))
}

export function connectLiveUpdates<T>({
    path,
    getToken,
    schema,
    onData,
    onDeleted,
    onUnavailable,
    onConnectionChange,
}: LiveSocketOptions<T>): () => void {
    let stopped = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let connectionTimer: number | null = null
    let livenessTimer: number | null = null
    let lastMessageAt = 0
    let connectionState: LiveConnectionState | null = null
    let isGettingToken = false
    let attempts = 0
    let refreshAttempted = false
    let forceRefresh = false

    const setConnectionState = (state: LiveConnectionState) => {
        if (connectionState === state) return
        connectionState = state
        onConnectionChange?.(state)
    }

    const clearSocketTimers = () => {
        if (connectionTimer !== null) {
            window.clearTimeout(connectionTimer)
            connectionTimer = null
        }
        if (livenessTimer !== null) {
            window.clearTimeout(livenessTimer)
            livenessTimer = null
        }
    }

    const scheduleReconnect = () => {
        if (stopped || reconnectTimer !== null || socket || isGettingToken)
            return
        setConnectionState("reconnecting")
        const baseDelay = Math.min(
            MAX_RECONNECT_DELAY_MS,
            500 * 2 ** Math.min(attempts, 5)
        )
        const delay = Math.round(
            baseDelay *
                (1 - RECONNECT_JITTER + Math.random() * RECONNECT_JITTER * 2)
        )
        attempts += 1
        reconnectTimer = window.setTimeout(() => {
            reconnectTimer = null
            void connect()
        }, delay)
    }

    /**
     * Gives up on the current socket without waiting for its close event,
     * which a dead connection may never send, and reconnects.
     */
    const abandonSocket = (immediately: boolean) => {
        const abandoned = socket
        if (!abandoned) return
        socket = null
        clearSocketTimers()
        // close() only accepts 1000 or 3000-4999, so pass no code at all.
        try {
            abandoned.close()
        } catch {
            // Already closing: the reconnect below does not depend on it.
        }
        if (immediately) {
            setConnectionState("reconnecting")
            attempts = 0
            void connect()
        } else {
            scheduleReconnect()
        }
    }

    const watchLiveness = (currentSocket: WebSocket) => {
        lastMessageAt = Date.now()
        if (livenessTimer !== null) window.clearTimeout(livenessTimer)
        livenessTimer = window.setTimeout(() => {
            livenessTimer = null
            if (socket === currentSocket) abandonSocket(false)
        }, LIVENESS_TIMEOUT_MS)
    }

    const connect = async () => {
        if (stopped || socket || isGettingToken) return
        isGettingToken = true
        let token: string | null
        try {
            token = await getToken(forceRefresh)
        } catch {
            forceRefresh = false
            isGettingToken = false
            scheduleReconnect()
            return
        }
        forceRefresh = false
        isGettingToken = false
        if (stopped) return
        if (!token) {
            onUnavailable()
            return
        }
        let currentSocket: WebSocket
        try {
            currentSocket = new WebSocket(apiWebSocketUrl(path))
        } catch {
            scheduleReconnect()
            return
        }
        socket = currentSocket
        connectionTimer = window.setTimeout(() => {
            connectionTimer = null
            if (socket === currentSocket) abandonSocket(false)
        }, CONNECTION_TIMEOUT_MS)
        currentSocket.addEventListener("open", () => {
            currentSocket.send(JSON.stringify({ token }))
        })
        currentSocket.addEventListener("message", (event) => {
            if (stopped || socket !== currentSocket) return
            let parsed: unknown
            try {
                parsed = JSON.parse(String(event.data))
            } catch {
                return
            }
            const envelope = v.safeParse(LiveMessageSchema, parsed)
            if (!envelope.success) {
                ignoreMalformedUpdate(path, envelope.issues)
                return
            }
            const message = envelope.output
            if (connectionTimer !== null) {
                window.clearTimeout(connectionTimer)
                connectionTimer = null
            }
            // Every message, pings included, proves the connection alive.
            watchLiveness(currentSocket)
            setConnectionState("connected")
            if (message.type === "ping") {
                attempts = 0
                refreshAttempted = false
                return
            }
            if (message.type === "deleted") {
                onDeleted?.()
                return
            }
            attempts = 0
            refreshAttempted = false
            if (!schema) {
                // A feed without a schema is trusted as its caller types it.
                onData(message.data as T)
                return
            }
            const data = v.safeParse(schema, message.data)
            if (data.success) onData(data.output)
            else ignoreMalformedUpdate(path, data.issues)
        })
        currentSocket.addEventListener("close", (event) => {
            // An abandoned socket was already replaced.
            if (socket !== currentSocket) return
            socket = null
            clearSocketTimers()
            if (stopped || event.code === 1000) return
            if (event.code === 1008) {
                if (!refreshAttempted) {
                    refreshAttempted = true
                    forceRefresh = true
                    scheduleReconnect()
                } else {
                    onUnavailable()
                }
                return
            }
            scheduleReconnect()
        })
        currentSocket.addEventListener("error", () => currentSocket.close())
    }

    const reconnectWhenOnline = () => {
        if (stopped) return
        if (socket) {
            // A connection that still delivers is kept; a silent one may be
            // half-open and is replaced now rather than at the watchdog.
            if (
                lastMessageAt > 0 &&
                Date.now() - lastMessageAt > STALE_AFTER_MS
            )
                abandonSocket(true)
            return
        }
        attempts = 0
        if (reconnectTimer !== null) {
            window.clearTimeout(reconnectTimer)
            reconnectTimer = null
        }
        void connect()
    }

    const reconnectWhenVisible = () => {
        if (document.visibilityState === "visible") reconnectWhenOnline()
    }

    window.addEventListener("online", reconnectWhenOnline)
    document.addEventListener("visibilitychange", reconnectWhenVisible)
    void connect()
    return () => {
        stopped = true
        if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
        clearSocketTimers()
        window.removeEventListener("online", reconnectWhenOnline)
        document.removeEventListener("visibilitychange", reconnectWhenVisible)
        socket?.close(1000)
    }
}

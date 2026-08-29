import { apiWebSocketUrl } from "@/api/client"

type LiveMessage<T> =
    { type: "ping" } | { type: "deleted" } | { type: string; data: T }

type LiveSocketOptions<T> = {
    path: string
    getToken: (forceRefresh: boolean) => Promise<string | null>
    onData: (data: T) => void
    onDeleted?: () => void
    onUnavailable: () => void
}

const MAX_RECONNECT_DELAY_MS = 10_000
const CONNECTION_TIMEOUT_MS = 10_000
const RECONNECT_JITTER = 0.25

export function connectLiveUpdates<T>({
    path,
    getToken,
    onData,
    onDeleted,
    onUnavailable,
}: LiveSocketOptions<T>): () => void {
    let stopped = false
    let socket: WebSocket | null = null
    let reconnectTimer: number | null = null
    let connectionTimer: number | null = null
    let isGettingToken = false
    let attempts = 0
    let refreshAttempted = false
    let forceRefresh = false

    const scheduleReconnect = () => {
        if (stopped || reconnectTimer !== null || socket || isGettingToken)
            return
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
            if (socket === currentSocket) {
                // close() only accepts 1000 or 3000-4999, so pass no code at
                // all: the close listener below schedules the reconnect once
                // the abandoned handshake reports 1006.
                try {
                    currentSocket.close()
                } catch {
                    socket = null
                    scheduleReconnect()
                }
            }
        }, CONNECTION_TIMEOUT_MS)
        currentSocket.addEventListener("open", () => {
            currentSocket.send(JSON.stringify({ token }))
        })
        currentSocket.addEventListener("message", (event) => {
            if (stopped) return
            let message: LiveMessage<T>
            try {
                message = JSON.parse(String(event.data)) as LiveMessage<T>
            } catch {
                return
            }
            if (connectionTimer !== null) {
                window.clearTimeout(connectionTimer)
                connectionTimer = null
            }
            if (message.type === "ping") {
                attempts = 0
                refreshAttempted = false
                return
            }
            if (message.type === "deleted") {
                onDeleted?.()
                return
            }
            if ("data" in message) {
                attempts = 0
                refreshAttempted = false
                onData(message.data)
            }
        })
        currentSocket.addEventListener("close", (event) => {
            if (socket === currentSocket) socket = null
            if (connectionTimer !== null) {
                window.clearTimeout(connectionTimer)
                connectionTimer = null
            }
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
        attempts = 0
        if (reconnectTimer !== null) {
            window.clearTimeout(reconnectTimer)
            reconnectTimer = null
        }
        void connect()
    }

    window.addEventListener("online", reconnectWhenOnline)
    void connect()
    return () => {
        stopped = true
        if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
        if (connectionTimer !== null) window.clearTimeout(connectionTimer)
        window.removeEventListener("online", reconnectWhenOnline)
        socket?.close(1000)
    }
}

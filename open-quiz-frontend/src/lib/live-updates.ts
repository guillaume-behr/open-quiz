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
    let attempts = 0
    let refreshAttempted = false
    let forceRefresh = false

    const scheduleReconnect = () => {
        if (stopped) return
        const delay = Math.min(
            MAX_RECONNECT_DELAY_MS,
            500 * 2 ** Math.min(attempts, 5)
        )
        attempts += 1
        reconnectTimer = window.setTimeout(() => void connect(), delay)
    }

    const connect = async () => {
        let token: string | null
        try {
            token = await getToken(forceRefresh)
        } catch {
            forceRefresh = false
            scheduleReconnect()
            return
        }
        forceRefresh = false
        if (stopped) return
        if (!token) {
            onUnavailable()
            return
        }
        const currentSocket = new WebSocket(apiWebSocketUrl(path))
        socket = currentSocket
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
            if (message.type === "ping") {
                attempts = 0
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

    void connect()
    return () => {
        stopped = true
        if (reconnectTimer !== null) window.clearTimeout(reconnectTimer)
        socket?.close(1000)
    }
}

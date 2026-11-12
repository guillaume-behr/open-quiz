// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
    connectLiveUpdates,
    LIVENESS_TIMEOUT_MS,
    type LiveConnectionState,
} from "./live-updates"

/** A WebSocket the test drives by hand: nothing reaches the network. */
class FakeSocket {
    static instances: FakeSocket[] = []
    readonly url: string
    readonly sent: string[] = []
    readonly closeCalls: (number | undefined)[] = []
    private listeners = new Map<string, ((event: unknown) => void)[]>()

    constructor(url: string) {
        this.url = url
        FakeSocket.instances.push(this)
    }

    addEventListener(type: string, listener: (event: unknown) => void) {
        this.listeners.set(type, [
            ...(this.listeners.get(type) ?? []),
            listener,
        ])
    }

    send(data: string) {
        this.sent.push(data)
    }

    /** Records the call only: a half-open connection never reports back. */
    close(code?: number) {
        this.closeCalls.push(code)
    }

    emit(type: string, event: unknown = {}) {
        for (const listener of this.listeners.get(type) ?? []) listener(event)
    }

    open() {
        this.emit("open")
    }

    receive(message: unknown) {
        this.emit("message", { data: JSON.stringify(message) })
    }

    serverClose(code: number) {
        this.emit("close", { code })
    }
}

function sockets() {
    return FakeSocket.instances
}

function lastSocket() {
    const socket = sockets().at(-1)
    if (!socket) throw new Error("No socket was opened")
    return socket
}

/** Lets the awaited token and the timers due within `ms` run. */
async function advance(ms: number) {
    await vi.advanceTimersByTimeAsync(ms)
}

let disconnect: (() => void) | null = null

function connect(
    overrides: {
        onDeleted?: () => void
        getToken?: (forceRefresh: boolean) => Promise<string | null>
    } = {}
) {
    const options = {
        path: "/api/quizzes/live/teacher/sessions",
        getToken: vi.fn(async () => "access-token"),
        onData: vi.fn(),
        onUnavailable: vi.fn(),
        onConnectionChange: vi.fn<(state: LiveConnectionState) => void>(),
        ...overrides,
    }
    disconnect = connectLiveUpdates<string>(options)
    return options
}

/** Opens the current socket and completes the handshake with a ping. */
function handshake() {
    lastSocket().open()
    lastSocket().receive({ type: "ping" })
}

beforeEach(() => {
    vi.useFakeTimers()
    // No jitter: each reconnect delay is exactly its backoff step.
    vi.spyOn(Math, "random").mockReturnValue(0.5)
    vi.stubGlobal("WebSocket", FakeSocket)
    FakeSocket.instances = []
})

afterEach(() => {
    disconnect?.()
    disconnect = null
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    vi.useRealTimers()
})

describe("connectLiveUpdates", () => {
    it("sends the token in the first message, never in the URL", async () => {
        connect()
        await advance(0)

        lastSocket().open()

        expect(lastSocket().url).not.toContain("access-token")
        expect(lastSocket().sent).toEqual([
            JSON.stringify({ token: "access-token" }),
        ])
    })

    it("abandons a handshake that gets no first message", async () => {
        connect()
        await advance(0)
        lastSocket().open()

        await advance(10_000)

        expect(sockets()[0].closeCalls).toEqual([undefined])
        sockets()[0].serverClose(1006)
        await advance(500)
        expect(sockets()).toHaveLength(2)
    })

    it("keeps a connection whose pings keep arriving", async () => {
        const options = connect()
        await advance(0)
        handshake()

        for (let elapsed = 0; elapsed < 180_000; elapsed += 25_000) {
            await advance(25_000)
            lastSocket().receive({ type: "ping" })
        }

        expect(sockets()).toHaveLength(1)
        expect(sockets()[0].closeCalls).toEqual([])
        expect(options.onConnectionChange.mock.calls).toEqual([["connected"]])
    })

    it("reconnects after a silence even when the socket never reports closing", async () => {
        const options = connect()
        await advance(0)
        handshake()

        await advance(LIVENESS_TIMEOUT_MS - 1)
        expect(sockets()[0].closeCalls).toEqual([])
        await advance(1)

        expect(sockets()[0].closeCalls).toEqual([undefined])
        expect(options.onConnectionChange).toHaveBeenLastCalledWith(
            "reconnecting"
        )
        await advance(500)
        expect(sockets()).toHaveLength(2)

        handshake()
        expect(options.onConnectionChange).toHaveBeenLastCalledWith("connected")
        // The abandoned socket reporting its close later changes nothing.
        sockets()[0].serverClose(1006)
        await advance(10_000)
        expect(sockets()).toHaveLength(2)
    })

    it("waits longer after each failure and starts over after a message", async () => {
        connect()
        await advance(0)

        for (const delay of [500, 1_000, 2_000]) {
            lastSocket().serverClose(1006)
            const count = sockets().length
            await advance(delay - 1)
            expect(sockets()).toHaveLength(count)
            await advance(1)
            expect(sockets()).toHaveLength(count + 1)
        }

        handshake()
        lastSocket().serverClose(1006)
        await advance(500)
        expect(sockets()).toHaveLength(5)
    })

    it("delivers data and the deletion notice", async () => {
        const onDeleted = vi.fn()
        const options = connect({ onDeleted })
        await advance(0)
        lastSocket().open()

        lastSocket().receive({ type: "session", data: "state" })
        lastSocket().receive({ type: "deleted" })

        expect(options.onData).toHaveBeenCalledWith("state")
        expect(onDeleted).toHaveBeenCalledOnce()
    })

    it("refreshes the token once when the server refuses it", async () => {
        const options = connect()
        await advance(0)

        lastSocket().serverClose(1008)
        await advance(500)
        expect(options.getToken).toHaveBeenLastCalledWith(true)
        expect(options.onUnavailable).not.toHaveBeenCalled()

        lastSocket().serverClose(1008)
        await advance(10_000)
        expect(options.onUnavailable).toHaveBeenCalledOnce()
        expect(sockets()).toHaveLength(2)
    })

    it("reconnects at once when a stale tab becomes visible again", async () => {
        connect()
        await advance(0)
        handshake()

        // Background tabs throttle timers: the watchdog has not fired yet.
        vi.setSystemTime(Date.now() + 40_000)
        document.dispatchEvent(new Event("visibilitychange"))
        await advance(0)

        expect(sockets()[0].closeCalls).toEqual([undefined])
        expect(sockets()).toHaveLength(2)
    })

    it("keeps a fresh connection when the tab becomes visible or the network returns", async () => {
        connect()
        await advance(0)
        handshake()

        await advance(10_000)
        document.dispatchEvent(new Event("visibilitychange"))
        window.dispatchEvent(new Event("online"))
        await advance(0)

        expect(sockets()).toHaveLength(1)
        expect(sockets()[0].closeCalls).toEqual([])
    })

    it("reconnects at once when the network returns to a stale connection", async () => {
        connect()
        await advance(0)
        handshake()

        vi.setSystemTime(Date.now() + 40_000)
        window.dispatchEvent(new Event("online"))
        await advance(0)

        expect(sockets()).toHaveLength(2)
    })

    it("leaves no timer or listener behind once unsubscribed", async () => {
        const removeWindowListener = vi.spyOn(window, "removeEventListener")
        const removeDocumentListener = vi.spyOn(document, "removeEventListener")
        connect()
        await advance(0)
        handshake()

        disconnect?.()
        disconnect = null

        expect(vi.getTimerCount()).toBe(0)
        expect(sockets()[0].closeCalls).toEqual([1000])
        expect(removeWindowListener).toHaveBeenCalledWith(
            "online",
            expect.any(Function)
        )
        expect(removeDocumentListener).toHaveBeenCalledWith(
            "visibilitychange",
            expect.any(Function)
        )
        // Nothing reconnects afterwards.
        document.dispatchEvent(new Event("visibilitychange"))
        await advance(LIVENESS_TIMEOUT_MS)
        expect(sockets()).toHaveLength(1)
    })

    it("retries a failed token request and stops without a token", async () => {
        const getToken = vi
            .fn<(forceRefresh: boolean) => Promise<string | null>>()
            .mockRejectedValueOnce(new Error("offline"))
            .mockResolvedValueOnce(null)
        const options = connect({ getToken })
        await advance(0)
        expect(sockets()).toHaveLength(0)
        expect(options.onConnectionChange).toHaveBeenLastCalledWith(
            "reconnecting"
        )
        await advance(500)
        expect(options.onUnavailable).toHaveBeenCalledOnce()
        expect(sockets()).toHaveLength(0)
    })

    it("does nothing once unsubscribed while the token is on its way", async () => {
        let deliver: (token: string) => void = () => undefined
        connect({
            getToken: () => new Promise((resolve) => (deliver = resolve)),
        })
        disconnect?.()
        disconnect = null
        deliver("late")
        await advance(0)
        expect(sockets()).toHaveLength(0)
    })

    it("retries when the WebSocket cannot even be created", async () => {
        vi.stubGlobal(
            "WebSocket",
            vi.fn(() => {
                throw new Error("blocked")
            })
        )
        const options = connect()
        await advance(0)
        expect(options.onConnectionChange).toHaveBeenLastCalledWith(
            "reconnecting"
        )
        vi.stubGlobal("WebSocket", FakeSocket)
        await advance(500)
        expect(sockets()).toHaveLength(1)
    })

    it("ignores unreadable messages and stops on a normal close", async () => {
        const options = connect()
        await advance(0)
        lastSocket().open()
        lastSocket().emit("message", { data: "{not json" })
        expect(options.onConnectionChange).not.toHaveBeenCalledWith("connected")
        lastSocket().receive({ type: "ping" })
        lastSocket().serverClose(1000)
        await advance(20_000)
        expect(sockets()).toHaveLength(1)
        lastSocket().emit("error")
        expect(lastSocket().closeCalls).toEqual([undefined])
    })

    it("reconnects at once when the network returns during a backoff", async () => {
        connect()
        await advance(0)
        handshake()
        lastSocket().serverClose(1006)
        await advance(0)
        window.dispatchEvent(new Event("online"))
        await advance(0)
        expect(sockets()).toHaveLength(2)
    })

    it("abandons a socket whose close() throws and clears a pending backoff", async () => {
        connect()
        await advance(0)
        handshake()
        lastSocket().close = () => {
            throw new Error("already closing")
        }
        await advance(LIVENESS_TIMEOUT_MS)
        expect(sockets()).toHaveLength(1)
        disconnect?.()
        disconnect = null
        await advance(20_000)
        expect(sockets()).toHaveLength(1)
    })
})

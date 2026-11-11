// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"

import { restoreSession } from "@/api/auth"
import {
    clearSessionTokens,
    getLiveAccessToken,
    onSessionExpired,
    request,
    setSessionTokens,
} from "@/api/client"
import { importQuestionBatch } from "@/api/question-banks"

const teacher = {
    id: 7,
    username: "grace",
    display_name: "Grace Hopper",
    is_admin: false,
    is_active: true,
    created_at: "2026-01-02T00:00:00Z",
}

function jwtExpiringIn(seconds: number): string {
    const payload = btoa(
        JSON.stringify({ exp: Math.floor(Date.now() / 1000) + seconds })
    )
    return `header.${payload}.signature`
}

function stubFetch(answer: (path: string) => Response) {
    const calls: string[] = []
    vi.stubGlobal(
        "fetch",
        vi.fn((input: RequestInfo | URL) => {
            const path = new URL(String(input), "http://localhost").pathname
            calls.push(path)
            return Promise.resolve(answer(path))
        })
    )
    return calls
}

afterEach(() => {
    vi.unstubAllGlobals()
    clearSessionTokens()
})

describe("staff session restore", () => {
    it("uses a fresh access token in memory without rotating the session", async () => {
        setSessionTokens(jwtExpiringIn(600), "proof")
        const calls = stubFetch(() => Response.json(teacher))

        await expect(restoreSession()).resolves.toEqual(teacher)

        expect(calls).toEqual(["/api/users/me"])
    })

    it("renews an access token about to expire", async () => {
        setSessionTokens(jwtExpiringIn(30), "proof")
        const calls = stubFetch((path) =>
            path === "/api/auth/refresh"
                ? Response.json({
                      access_token: jwtExpiringIn(900),
                      refresh_proof: "next-proof",
                  })
                : Response.json(teacher)
        )

        await restoreSession()

        expect(calls).toEqual(["/api/auth/refresh", "/api/users/me"])
    })

    it("reports an expired session exactly once", async () => {
        setSessionTokens(jwtExpiringIn(-60), "proof")
        stubFetch(() => new Response(null, { status: 401 }))
        const expired = vi.fn()
        const unsubscribe = onSessionExpired(expired)

        await expect(
            Promise.all([getLiveAccessToken(true), getLiveAccessToken(true)])
        ).resolves.toEqual([null, null])
        await getLiveAccessToken(true)

        expect(expired).toHaveBeenCalledTimes(1)
        unsubscribe()
    })
})

describe("request timeouts", () => {
    afterEach(() => {
        vi.restoreAllMocks()
        vi.unstubAllGlobals()
        clearSessionTokens()
    })

    function stubFetchSignals(statuses: number[]) {
        const signals: AbortSignal[] = []
        vi.stubGlobal(
            "fetch",
            vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
                const path = new URL(String(input), "http://localhost").pathname
                if (path === "/api/auth/refresh")
                    return Promise.resolve(
                        Response.json({
                            access_token: jwtExpiringIn(900),
                            refresh_proof: "next-proof",
                        })
                    )
                if (init?.signal) signals.push(init.signal)
                const status = statuses.shift() ?? 200
                return Promise.resolve(
                    status === 204
                        ? new Response(null, { status })
                        : Response.json({}, { status })
                )
            })
        )
        return signals
    }

    it("keeps the timeout when the caller passes its own signal", async () => {
        const timeouts: AbortController[] = []
        vi.spyOn(AbortSignal, "timeout").mockImplementation(() => {
            const controller = new AbortController()
            timeouts.push(controller)
            return controller.signal
        })
        const signals = stubFetchSignals([204])
        const caller = new AbortController()

        await request("/api/anything", { signal: caller.signal })

        expect(signals[0]?.aborted).toBe(false)
        timeouts[0]?.abort()
        expect(signals[0]?.aborted).toBe(true)
    })

    it("still lets the caller abort", async () => {
        const signals = stubFetchSignals([204])
        const caller = new AbortController()

        await request("/api/anything", { signal: caller.signal })

        caller.abort()
        expect(signals[0]?.aborted).toBe(true)
    })

    it("gives a retried request a timeout of its own", async () => {
        const timeouts: AbortController[] = []
        vi.spyOn(AbortSignal, "timeout").mockImplementation(() => {
            const controller = new AbortController()
            timeouts.push(controller)
            return controller.signal
        })
        setSessionTokens(jwtExpiringIn(900), "proof")
        const signals = stubFetchSignals([401, 204])

        await importQuestionBatch(
            new File(['{"question_bank": {}}'], "bank.json", {
                type: "application/json",
            })
        ).catch(() => undefined)

        expect(signals).toHaveLength(2)
        expect(signals[1]).not.toBe(signals[0])
        // The first attempt's timer running out no longer matters.
        timeouts[0]?.abort()
        expect(signals[1]?.aborted).toBe(false)
    })
})

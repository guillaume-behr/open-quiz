// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"

import { restoreSession } from "@/api/auth"
import {
    clearSessionTokens,
    getLiveAccessToken,
    onSessionExpired,
    setSessionTokens,
} from "@/api/client"

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

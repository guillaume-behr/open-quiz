// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"

import { login, restoreSession, verifyTwoFactor } from "@/api/auth"
import {
    ApiError,
    UNEXPECTED_RESPONSE_CODE,
    apiWebSocketUrl,
    clearSessionTokens,
    getLiveAccessToken,
    onSessionExpired,
    refreshProofHeaders,
    request,
    requestBlob,
    requestPage,
    setSessionTokens,
} from "@/api/client"
import { importQuestionBatch } from "@/api/question-banks"
import { apiErrorMessage } from "@/lib/errors"

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
            const path = new URL(
                input instanceof Request ? input.url : input,
                "http://localhost"
            ).pathname
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

describe("response validation", () => {
    function expectUnexpectedResponse(error: unknown) {
        expect(error).toBeInstanceOf(ApiError)
        expect(error).toMatchObject({
            code: UNEXPECTED_RESPONSE_CODE,
            status: 200,
        })
        expect(apiErrorMessage(error, (key) => key, "fallback")).toBe(
            "error-unexpected-response"
        )
    }

    it("refuses a current user of the wrong shape", async () => {
        setSessionTokens(jwtExpiringIn(600), "proof")
        stubFetch(() => Response.json({ ...teacher, is_admin: "no" }))

        expectUnexpectedResponse(
            await restoreSession().catch((error: unknown) => error)
        )
    })

    it("refuses a renewal without tokens and keeps the old session", async () => {
        setSessionTokens(jwtExpiringIn(30), "proof")
        stubFetch(() => Response.json({ access_token: "token-only" }))

        expectUnexpectedResponse(
            await restoreSession().catch((error: unknown) => error)
        )
        expect(refreshProofHeaders()).toEqual({ "X-Refresh-Proof": "proof" })
    })

    it("refuses a login answer it cannot tell apart", async () => {
        stubFetch(() => Response.json({ status: "authenticated" }))

        expectUnexpectedResponse(
            await login("grace", "secret", "professor").catch(
                (error: unknown) => error
            )
        )
    })

    it("refuses a body that is not JSON", async () => {
        stubFetch(() => new Response("<html>", { status: 200 }))

        expectUnexpectedResponse(
            await verifyTwoFactor("challenge", "123456").catch(
                (error: unknown) => error
            )
        )
    })

    it("signs in from a challenge-free login", async () => {
        const calls = stubFetch((path) =>
            path === "/api/auth/login"
                ? Response.json({
                      status: "authenticated",
                      access_token: jwtExpiringIn(900),
                      refresh_proof: "proof",
                      token_type: "bearer",
                  })
                : Response.json(teacher)
        )

        await expect(login("grace", "secret", "professor")).resolves.toEqual({
            status: "authenticated",
            user: teacher,
        })
        expect(calls).toEqual(["/api/auth/login", "/api/users/me"])
    })

    it("returns a two-factor challenge with the backend defaults", async () => {
        stubFetch(() =>
            Response.json({
                status: "verification_required",
                challenge_token: "challenge",
            })
        )

        await expect(login("grace", "secret", "admin")).resolves.toEqual({
            status: "verification_required",
            challenge_token: "challenge",
            secret: null,
            provisioning_uri: null,
        })
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
                const path = new URL(
                    input instanceof Request ? input.url : input,
                    "http://localhost"
                ).pathname
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

describe("requests and errors", () => {
    function json(body: unknown, status = 200, headers: HeadersInit = {}) {
        return new Response(status === 204 ? null : JSON.stringify(body), {
            status,
            headers,
        })
    }

    it("maps API errors to their status, code and message", async () => {
        const answers = [
            json({ detail: { code: "QUIZ_NOT_FOUND", message: "x" } }, 404),
            json({ detail: "Plain message" }, 400),
            json({ detail: [{ loc: ["body"], msg: "bad" }] }, 422),
            new Response("not json", { status: 500 }),
        ]
        stubFetch(() => answers.shift() ?? json({}))
        await expect(request("/api/a")).rejects.toMatchObject({
            status: 404,
            code: "QUIZ_NOT_FOUND",
            message: "QUIZ_NOT_FOUND",
        })
        await expect(request("/api/a")).rejects.toMatchObject({
            status: 400,
            code: null,
            message: "Plain message",
        })
        await expect(request("/api/a")).rejects.toMatchObject({
            status: 422,
            message: "Request failed with status 422",
        })
        await expect(request("/api/a")).rejects.toBeInstanceOf(ApiError)
    })

    it("returns nothing for 204, pages from headers and blobs", async () => {
        const answers = [
            json(null, 204),
            json(["a", "b"], 200, {
                "X-Page": "2",
                "X-Page-Size": "2",
                "X-Total-Count": "5",
            }),
            json(["a"]),
            new Response("file"),
        ]
        stubFetch(() => answers.shift() ?? json({}))
        await expect(request("/api/a")).resolves.toBeUndefined()
        await expect(requestPage("/api/a")).resolves.toEqual({
            items: ["a", "b"],
            page: 2,
            pageSize: 2,
            total: 5,
            totalPages: 3,
        })
        await expect(requestPage("/api/a")).resolves.toMatchObject({
            page: 1,
            pageSize: 1,
            totalPages: 1,
        })
        await expect((await requestBlob("/api/a")).text()).resolves.toBe("file")
    })

    it("falls back on malformed paging headers instead of NaN", async () => {
        stubFetch(() =>
            json(["a", "b"], 200, {
                "X-Page": "two",
                "X-Page-Size": "0",
                "X-Total-Count": "-3",
            })
        )
        await expect(requestPage("/api/a")).resolves.toEqual({
            items: ["a", "b"],
            page: 1,
            pageSize: 2,
            total: 2,
            totalPages: 1,
        })
    })

    it("refreshes once on 401 for concurrent requests, then retries", async () => {
        setSessionTokens("old", "proof")
        let refreshes = 0
        const calls = stubFetch((path) => {
            if (path === "/api/auth/refresh") {
                refreshes += 1
                return json({ access_token: "new", refresh_proof: "proof2" })
            }
            return calls.filter((call) => call === path).length > 1
                ? json({ ok: path })
                : json({}, 401)
        })
        const results = await Promise.all([
            request("/api/a"),
            request("/api/b"),
        ])
        expect(results).toEqual([{ ok: "/api/a" }, { ok: "/api/b" }])
        expect(refreshes).toBe(1)
        expect(refreshProofHeaders()).toEqual({ "X-Refresh-Proof": "proof2" })
    })

    it("surfaces a failing refresh and works without session storage", async () => {
        setSessionTokens("old", "proof")
        stubFetch((path) =>
            path === "/api/auth/refresh"
                ? json({ detail: "down" }, 500)
                : json({}, 401)
        )
        await expect(request("/api/a")).rejects.toMatchObject({ status: 500 })

        vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
            throw new Error("blocked")
        })
        expect(() => setSessionTokens("a", "p")).not.toThrow()
        expect(refreshProofHeaders()).toEqual({ "X-Refresh-Proof": "p" })
        clearSessionTokens()
        expect(refreshProofHeaders()).toEqual({})
        await expect(request("/api/a")).rejects.toMatchObject({ status: 401 })
    })

    it("builds WebSocket URLs from the page's origin", () => {
        expect(apiWebSocketUrl("/api/live")).toBe(
            `ws://${window.location.host}/api/live`
        )
    })
})

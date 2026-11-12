import { beforeEach, describe, expect, it, vi } from "vitest"

import * as quizzes from "./quizzes"

const client = vi.hoisted(() => ({
    request: vi.fn(),
    requestBlob: vi.fn(),
    requestPage: vi.fn(),
}))
vi.mock("./client", () => client)

function lastUrl(mock: ReturnType<typeof vi.fn>): string {
    return String(mock.mock.calls.at(-1)?.[0])
}

describe("quiz API", () => {
    beforeEach(() => {
        client.request.mockResolvedValue({})
        client.requestBlob.mockResolvedValue(new Blob())
        client.requestPage.mockImplementation((url: string) =>
            Promise.resolve({
                items: [url],
                page: 1,
                pageSize: 100,
                total: 3,
                totalPages: 3,
            })
        )
    })

    it("builds the quiz list query and walks every page", async () => {
        await quizzes.getQuizzes(2, "alg", "Tle", 10, 7)
        expect(lastUrl(client.requestPage)).toBe(
            "/api/quizzes?page=2&page_size=10&mode=exam&search=alg&grade_level=Tle&focus=7"
        )
        await quizzes.getQuizzes()
        expect(lastUrl(client.requestPage)).toBe(
            "/api/quizzes?page=1&page_size=8&mode=exam"
        )
        const all = await quizzes.getAllQuizzes()
        expect(all).toHaveLength(3)
        expect(lastUrl(client.requestPage)).toContain("page=3&page_size=100")
    })

    it("builds result queries and exports", async () => {
        await quizzes.getQuizResults(3, {
            quizSearch: "q",
            classId: "4",
            startedFrom: new Date("2026-01-05T00:00:00Z"),
            startedBefore: new Date("2026-01-12T00:00:00Z"),
        })
        expect(lastUrl(client.requestPage)).toBe(
            "/api/quizzes/sessions/results?page=3&page_size=8&quiz_search=q&class_id=4" +
                "&started_from=2026-01-05T00%3A00%3A00.000Z&started_before=2026-01-12T00%3A00%3A00.000Z"
        )
        await quizzes.getQuizResults()
        expect(lastUrl(client.requestPage)).toBe(
            "/api/quizzes/sessions/results?page=1&page_size=8"
        )
        await quizzes.downloadQuizResults(4, 9)
        expect(lastUrl(client.requestBlob)).toBe(
            "/api/quizzes/sessions/results/export?class_id=4&quiz_id=9"
        )
        await quizzes.downloadQuizResults(4, null)
        expect(lastUrl(client.requestBlob)).toBe(
            "/api/quizzes/sessions/results/export?class_id=4"
        )
    })

    it("sends every other call to an /api/quizzes URL", async () => {
        const skipped = new Set([
            "getQuizzes",
            "getAllQuizzes",
            "getQuizResults",
            "downloadQuizResults",
        ])
        const calls = Object.entries(quizzes).filter(
            ([name, value]) => typeof value === "function" && !skipped.has(name)
        ) as [string, (...args: unknown[]) => Promise<unknown>][]
        expect(calls.length).toBeGreaterThan(20)
        for (const [name, call] of calls) {
            vi.clearAllMocks()
            await call(1, 2, 3, "text", 5)
            const urls = [
                client.request,
                client.requestBlob,
                client.requestPage,
            ]
                .flatMap((mock) => mock.mock.calls)
                .map((args) => String(args[0]))
            expect(urls, name).toEqual([
                expect.stringMatching(/^\/api\/quizzes/),
            ])
        }
    })
})

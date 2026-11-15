import { beforeEach, describe, expect, it, vi } from "vitest"

import type { QuizSession } from "@/api/types"

import { loadResults, loadScheduleWeek } from "./results-loading"

const api = vi.hoisted(() => ({ getQuizResults: vi.fn() }))
vi.mock("@/api/quizzes", () => api)

const signal = new AbortController().signal
const filters = { quiz: "  alg ", class: "4" }
const query = { quizSearch: "alg", classId: "4" }

function page(items: Partial<QuizSession>[], total = items.length) {
    return { items, total, page: 1, pageSize: 1, totalPages: 1 }
}

describe("results loading", () => {
    beforeEach(() => {
        api.getQuizResults.mockReset()
    })

    it("loads a page of results with trimmed filters", async () => {
        api.getQuizResults.mockResolvedValue(page([]))
        await loadResults(2, filters, null, signal)
        expect(api.getQuizResults).toHaveBeenCalledWith(
            2,
            query,
            undefined,
            signal
        )
    })

    it("has no schedule without any result", async () => {
        api.getQuizResults.mockResolvedValue(page([]))
        await expect(loadScheduleWeek(filters, null, signal)).resolves.toBe(
            null
        )
    })

    it("loads the newest week, then an earlier one by date", async () => {
        const newest = {
            id: 1,
            started_at: "2026-03-12T10:00:00",
            created_at: "2026-03-12T09:00:00",
        }
        api.getQuizResults.mockImplementation(
            (_page: number, request: { startedFrom?: Date }) =>
                Promise.resolve(
                    request.startedFrom ? page([newest]) : page([newest], 3)
                )
        )
        const latest = await loadScheduleWeek(filters, null, signal)
        expect(latest).toMatchObject({
            results: [newest],
            hasEarlier: true,
            hasLater: false,
        })
        expect(latest?.weekStart.getDay()).toBe(1)
        expect(api.getQuizResults).toHaveBeenCalledWith(
            1,
            {
                ...query,
                startedFrom: latest?.weekStart,
                startedBefore: expect.any(Date) as Date,
            },
            100,
            signal
        )

        const earlierWeek = new Date(2026, 2, 2)
        const earlier = await loadScheduleWeek(filters, earlierWeek, signal)
        expect(earlier).toMatchObject({
            weekStart: earlierWeek,
            hasLater: true,
        })
    })
})

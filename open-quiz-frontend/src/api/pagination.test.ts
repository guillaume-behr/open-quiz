import { describe, expect, it, vi } from "vitest"

import { fetchAllPages } from "./pagination"

function page(number: number, totalPages: number) {
    return {
        items: [`item-${number}`],
        page: number,
        pageSize: 1,
        total: totalPages,
        totalPages,
    }
}

describe("fetchAllPages", () => {
    it("loads every page and keeps their order", async () => {
        const loadPage = vi.fn((number: number) =>
            Promise.resolve(page(number, 3))
        )
        await expect(fetchAllPages(loadPage)).resolves.toEqual([
            "item-1",
            "item-2",
            "item-3",
        ])
        expect(loadPage.mock.calls.map(([number]) => number)).toEqual([1, 2, 3])
    })

    it("stops after a single page", async () => {
        const loadPage = vi.fn(() => Promise.resolve(page(1, 1)))
        await expect(fetchAllPages(loadPage)).resolves.toEqual(["item-1"])
        expect(loadPage).toHaveBeenCalledTimes(1)
    })
})

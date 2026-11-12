// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { Page } from "@/api/types"

import { usePagedList } from "./use-paged-list"

type Filters = { search: string }

function page(number: number, totalPages: number): Page<string> {
    return {
        items: [`item-${number}`],
        page: number,
        pageSize: 1,
        total: totalPages,
        totalPages,
    } as Page<string>
}

describe("usePagedList", () => {
    it("pages, filters, resets and focuses", async () => {
        const load = vi.fn(
            (
                requested: number,
                _filters: Filters,
                focus: number | null
            ): Promise<Page<string>> =>
                Promise.resolve(page(focus === null ? requested : 3, 3))
        )
        const { result } = renderHook(() =>
            usePagedList(load, { search: "" } as Filters)
        )
        await waitFor(() => expect(result.current.items).toEqual(["item-1"]))
        expect(result.current.totalPages).toBe(3)

        act(() => result.current.showPage(2))
        await waitFor(() => expect(result.current.items).toEqual(["item-2"]))
        act(() => result.current.setFilter("search", "x"))
        expect(result.current.page).toBe(1)
        expect(result.current.filters).toEqual({ search: "x" })
        await waitFor(() => expect(result.current.isLoading).toBe(false))
        act(() => result.current.resetFilters())
        expect(result.current.filters).toEqual({ search: "" })

        act(() => result.current.focus(42))
        await waitFor(() => expect(result.current.page).toBe(3))
        expect(load).toHaveBeenLastCalledWith(
            1,
            { search: "" },
            42,
            expect.any(AbortSignal)
        )
    })

    it("steps back when the current page falls past the end", async () => {
        let totalPages = 3
        const load = (requested: number) =>
            Promise.resolve(page(Math.min(requested, totalPages), totalPages))
        const { result } = renderHook(() =>
            usePagedList(load, {} as Record<string, string>)
        )
        act(() => result.current.showPage(3))
        await waitFor(() => expect(result.current.items).toEqual(["item-3"]))
        totalPages = 2
        act(() => result.current.reload())
        await waitFor(() => expect(result.current.page).toBe(2))
    })
})

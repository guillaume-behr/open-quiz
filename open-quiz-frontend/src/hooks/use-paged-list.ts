import { useCallback, useState } from "react"

import type { Page } from "@/api/types"
import { useResource, type Resource } from "@/hooks/use-resource"

export type PagedList<T, F extends Record<string, string>> = Resource<
    Page<T>
> & {
    /** Items of the page on screen, empty until the first load settles. */
    items: T[]
    /** The page on screen: the one the API chose while an item is focused. */
    page: number
    totalPages: number
    filters: F
    /** Changes one filter and goes back to the first page. */
    setFilter: (name: keyof F, value: string) => void
    /** Clears every filter and goes back to the first page. */
    resetFilters: () => void
    /** Shows another page, dropping any focused item. */
    showPage: (page: number) => void
    /**
     * Shows the page that holds this item, as the API places it, with the
     * filters cleared: a list whose filters hide a just-saved item would
     * leave it nowhere to be seen.
     */
    focus: (id: number) => void
}

/**
 * A paged, filtered list loaded from the API. `load` must be stable (defined
 * at module level, or memoized with useCallback): a new function reloads.
 * When `load` accepts a focused item, `focus()` asks the API for its page.
 * The signal aborts a load superseded by another page or filter.
 */
export function usePagedList<T, F extends Record<string, string>>(
    load: (
        page: number,
        filters: F,
        focus: number | null,
        signal: AbortSignal
    ) => Promise<Page<T>>,
    initialFilters: F
): PagedList<T, F> {
    const [defaultFilters] = useState(initialFilters)
    const [page, setPage] = useState(1)
    const [filters, setFilters] = useState(initialFilters)
    const [focusedId, setFocusedId] = useState<number | null>(null)
    const resource = useResource(
        useCallback(
            (signal: AbortSignal) => load(page, filters, focusedId, signal),
            [filters, focusedId, load, page]
        )
    )
    const totalPages = resource.data?.totalPages ?? 1
    // A deletion can leave the current page past the end of the list.
    if (focusedId === null && resource.data && page > totalPages) {
        setPage(totalPages)
    }

    const showPage = useCallback((nextPage: number) => {
        setFocusedId(null)
        setPage(nextPage)
    }, [])
    const setFilter = useCallback((name: keyof F, value: string) => {
        setFilters((current) => ({ ...current, [name]: value }))
        setFocusedId(null)
        setPage(1)
    }, [])
    const resetFilters = useCallback(() => {
        setFilters(defaultFilters)
        setFocusedId(null)
        setPage(1)
    }, [defaultFilters])
    const { reload } = resource
    const focus = useCallback(
        (id: number) => {
            setFilters(defaultFilters)
            setPage(1)
            setFocusedId(id)
            // The same id can be focused twice in a row, after two saves of
            // one item: reload even when no state changed.
            reload()
        },
        [defaultFilters, reload]
    )

    return {
        ...resource,
        items: resource.data?.items ?? [],
        page: focusedId === null ? page : (resource.data?.page ?? page),
        totalPages,
        filters,
        setFilter,
        resetFilters,
        showPage,
        focus,
    }
}

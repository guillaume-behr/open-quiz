import type { Page } from "./types"

/** The page size used to load a whole list, for pickers and exports. */
export const ALL_PAGES_SIZE = 100

/**
 * Loads every page of a list: the first one tells how many there are, the
 * others are then fetched in parallel. Items keep the order of the pages.
 */
export async function fetchAllPages<T>(
    loadPage: (page: number) => Promise<Page<T>>
): Promise<T[]> {
    const first = await loadPage(1)
    const rest = await Promise.all(
        Array.from({ length: first.totalPages - 1 }, (_, index) =>
            loadPage(index + 2)
        )
    )
    return [first, ...rest].flatMap((page) => page.items)
}

/** The first item, failing the test when there is none. */
export function first<T>(items: readonly T[]): T {
    const [item] = items
    if (item === undefined) throw new Error("Expected at least one item")
    return item
}

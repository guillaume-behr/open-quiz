import { type Dispatch, type SetStateAction, useEffect, useState } from "react"

function storedValue<T extends string>(
    key: string,
    allowed: readonly T[],
    fallback: T
): T {
    try {
        const stored = localStorage.getItem(key)
        return allowed.find((value) => value === stored) ?? fallback
    } catch {
        return fallback
    }
}

/**
 * A choice among `allowed` kept in this browser's storage under `key`, such
 * as a preferred view. Starts from `fallback` when nothing valid is stored.
 */
export function usePersistentState<T extends string>(
    key: string,
    allowed: readonly T[],
    fallback: T
): [T, Dispatch<SetStateAction<T>>] {
    const [value, setValue] = useState<T>(() =>
        storedValue(key, allowed, fallback)
    )

    useEffect(() => {
        try {
            localStorage.setItem(key, value)
        } catch {
            // The choice remains valid for this session if storage is unavailable.
        }
    }, [key, value])

    return [value, setValue]
}

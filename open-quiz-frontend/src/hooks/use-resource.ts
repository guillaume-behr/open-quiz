import { useCallback, useEffect, useState } from "react"

export type Resource<T> = {
    /** Last successfully loaded value, kept while a newer load runs. */
    data: T | undefined
    /** Error of the current load, cleared by the next success. */
    error: unknown
    /** True until the current loader and reload have settled. */
    isLoading: boolean
    /** True once any load has settled, successfully or not. */
    hasSettled: boolean
    /** Loads again, for instance after a mutation. */
    reload: () => void
    /** Replaces the loaded value locally, without a request. */
    setData: (update: (current: T | undefined) => T | undefined) => void
}

type Settled<T> = {
    load: (signal: AbortSignal) => Promise<T>
    version: number
    data: T | undefined
    error: unknown
}

/**
 * Loads the value `load` resolves to, again whenever `load` changes (memoize
 * it with useCallback) or `reload` is called. A superseded load is aborted
 * through the signal `load` receives, and its result dropped, so a slow
 * answer never overwrites a newer one.
 */
export function useResource<T>(
    load: (signal: AbortSignal) => Promise<T>
): Resource<T> {
    const [version, setVersion] = useState(0)
    const [settled, setSettled] = useState<Settled<T> | null>(null)

    useEffect(() => {
        let active = true
        const controller = new AbortController()
        load(controller.signal).then(
            (data) => {
                if (active) setSettled({ load, version, data, error: null })
            },
            (error: unknown) => {
                if (active)
                    setSettled((current) => ({
                        load,
                        version,
                        data: current?.data,
                        error,
                    }))
            }
        )
        return () => {
            active = false
            controller.abort()
        }
    }, [load, version])

    const reload = useCallback(() => setVersion((current) => current + 1), [])
    const setData = useCallback(
        (update: (current: T | undefined) => T | undefined) =>
            setSettled((current) =>
                current ? { ...current, data: update(current.data) } : current
            ),
        []
    )
    const isCurrent = settled?.load === load && settled.version === version

    return {
        data: settled?.data,
        error: isCurrent ? settled.error : null,
        isLoading: !isCurrent,
        hasSettled: settled !== null,
        reload,
        setData,
    }
}

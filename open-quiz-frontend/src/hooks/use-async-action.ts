import { useState } from "react"

export type AsyncAction<Args extends unknown[]> = {
    run: (...args: Args) => Promise<void>
    isPending: boolean
    error: string | null
    setError: (error: string | null) => void
}

/**
 * Tracks a user action that calls the API: whether it is running and the
 * message of its last failure. `describeError` turns a rejection into the
 * message shown to the user.
 */
export function useAsyncAction<Args extends unknown[]>(
    action: (...args: Args) => Promise<void>,
    describeError: (caught: unknown) => string
): AsyncAction<Args> {
    const [isPending, setIsPending] = useState(false)
    const [error, setError] = useState<string | null>(null)

    async function run(...args: Args): Promise<void> {
        setError(null)
        setIsPending(true)
        try {
            await action(...args)
        } catch (caught) {
            setError(describeError(caught))
        } finally {
            setIsPending(false)
        }
    }

    return { run, isPending, error, setError }
}

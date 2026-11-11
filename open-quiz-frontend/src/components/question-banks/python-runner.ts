const EXECUTION_TIMEOUT_MS = 10_000
const INITIALIZATION_TIMEOUT_MS = 60_000
const MAX_SOURCE_CHARACTERS = 20_000

/** Why the runner itself, not the program, failed. */
export type PythonRunnerFailure =
    | "timeout"
    | "crashed"
    | "source-too-long"
    | "init-timeout"
    | "output-too-long"

/** A failure of the runner, shown to the user in their language. */
export class PythonRunnerError extends Error {
    readonly reason: PythonRunnerFailure

    constructor(reason: PythonRunnerFailure) {
        super(`Python runner failure: ${reason}`)
        this.reason = reason
    }
}

/**
 * The text to show for a failed run: a runner failure in the user's language,
 * or the program's own error (a Python traceback) as Python wrote it.
 */
export function describePythonFailure(
    error: unknown,
    t: (key: string) => string
): string {
    if (error instanceof PythonRunnerError) {
        return t(`python-error-${error.reason}`)
    }
    return error instanceof Error ? error.message : String(error)
}

type RunResponse = {
    id: string
    started?: boolean
    output?: string
    error?: string
    fatal?: boolean
    outputLimitExceeded?: boolean
}

type PendingExecution = {
    resolve: (output: string) => void
    reject: (error: Error) => void
    timeout: number
    started: boolean
}

let worker: Worker | undefined
const pendingExecutions = new Map<string, PendingExecution>()

function stopWorker(error: Error) {
    worker?.terminate()
    worker = undefined
    for (const execution of pendingExecutions.values()) {
        window.clearTimeout(execution.timeout)
        execution.reject(error)
    }
    pendingExecutions.clear()
}

function getWorker(): Worker {
    if (worker) return worker
    worker = new Worker(new URL("./python-runner.worker.ts", import.meta.url), {
        type: "module",
    })
    worker.onmessage = (event: MessageEvent<RunResponse>) => {
        const execution = pendingExecutions.get(event.data.id)
        if (!execution) return
        if (event.data.started) {
            if (execution.started) return
            window.clearTimeout(execution.timeout)
            execution.started = true
            execution.timeout = window.setTimeout(() => {
                stopWorker(new PythonRunnerError("timeout"))
            }, EXECUTION_TIMEOUT_MS)
            return
        }
        window.clearTimeout(execution.timeout)
        pendingExecutions.delete(event.data.id)
        if (event.data.error !== undefined) {
            const error = event.data.outputLimitExceeded
                ? new PythonRunnerError("output-too-long")
                : new Error(event.data.error)
            execution.reject(error)
            if (event.data.fatal) stopWorker(error)
        } else {
            execution.resolve(event.data.output ?? "")
        }
    }
    worker.onerror = () => {
        stopWorker(new PythonRunnerError("crashed"))
    }
    return worker
}

export function runPython(source: string): Promise<string> {
    if (source.length > MAX_SOURCE_CHARACTERS) {
        return Promise.reject(new PythonRunnerError("source-too-long"))
    }
    const id = crypto.randomUUID()
    return new Promise((resolve, reject) => {
        const timeout = window.setTimeout(() => {
            stopWorker(new PythonRunnerError("init-timeout"))
        }, INITIALIZATION_TIMEOUT_MS)
        pendingExecutions.set(id, { resolve, reject, timeout, started: false })
        getWorker().postMessage({ id, source })
    })
}

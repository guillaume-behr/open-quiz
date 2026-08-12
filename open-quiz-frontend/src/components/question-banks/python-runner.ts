const EXECUTION_TIMEOUT_MS = 10_000
const INITIALIZATION_TIMEOUT_MS = 60_000
const MAX_SOURCE_CHARACTERS = 20_000

type RunResponse = {
    id: string
    started?: boolean
    output?: string
    error?: string
    fatal?: boolean
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
                stopWorker(new Error("Python execution exceeded 10 seconds."))
            }, EXECUTION_TIMEOUT_MS)
            return
        }
        window.clearTimeout(execution.timeout)
        pendingExecutions.delete(event.data.id)
        if (event.data.error !== undefined) {
            const error = new Error(event.data.error)
            execution.reject(error)
            if (event.data.fatal) stopWorker(error)
        } else {
            execution.resolve(event.data.output ?? "")
        }
    }
    worker.onerror = () => {
        stopWorker(new Error("The Python runtime stopped unexpectedly."))
    }
    return worker
}

export function runPython(source: string): Promise<string> {
    if (source.length > MAX_SOURCE_CHARACTERS) {
        return Promise.reject(
            new Error("Python source exceeded 20,000 characters.")
        )
    }
    const id = crypto.randomUUID()
    return new Promise((resolve, reject) => {
        const timeout = window.setTimeout(() => {
            stopWorker(
                new Error("The Python runtime could not be initialized.")
            )
        }, INITIALIZATION_TIMEOUT_MS)
        pendingExecutions.set(id, { resolve, reject, timeout, started: false })
        getWorker().postMessage({ id, source })
    })
}

const EXECUTION_TIMEOUT_MS = 10_000
const INITIALIZATION_TIMEOUT_MS = 60_000

type RunResponse = {
    id: number
    started?: boolean
    output?: string
    error?: string
}

type PendingExecution = {
    resolve: (output: string) => void
    reject: (error: Error) => void
    timeout: number
}

let worker: Worker | undefined
let nextExecutionId = 1
const pendingExecutions = new Map<number, PendingExecution>()

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
        window.clearTimeout(execution.timeout)
        if (event.data.started) {
            execution.timeout = window.setTimeout(() => {
                stopWorker(new Error("Python execution exceeded 10 seconds."))
            }, EXECUTION_TIMEOUT_MS)
            return
        }
        pendingExecutions.delete(event.data.id)
        if (event.data.error !== undefined) {
            execution.reject(new Error(event.data.error))
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
    const id = nextExecutionId++
    return new Promise((resolve, reject) => {
        const timeout = window.setTimeout(() => {
            stopWorker(
                new Error("The Python runtime could not be initialized.")
            )
        }, INITIALIZATION_TIMEOUT_MS)
        pendingExecutions.set(id, { resolve, reject, timeout })
        getWorker().postMessage({ id, source })
    })
}

/// <reference lib="webworker" />

type RunRequest = {
    id: number
    source: string
}

type RunResponse = {
    id: number
    started?: boolean
    output?: string
    error?: string
}

type PythonRuntime = {
    setStdout(options: { batched: (line: string) => void }): void
    setStderr(options: { batched: (line: string) => void }): void
    runPythonAsync(source: string): Promise<unknown>
}

type PyodideModule = {
    loadPyodide(options: { indexURL: string }): Promise<PythonRuntime>
}

const PYODIDE_MODULE_URL = "/pyodide/pyodide.asm.mjs"
let runtimePromise: Promise<PythonRuntime> | undefined
let networkDisabled = false

function denyNetworkAccess(): never {
    throw new Error("Network access is disabled for Python execution.")
}

function disableNetworkAccess() {
    if (networkDisabled) return
    for (const capability of [
        "fetch",
        "XMLHttpRequest",
        "WebSocket",
        "EventSource",
        "WebTransport",
        "RTCPeerConnection",
        "Worker",
        "SharedWorker",
        "importScripts",
        "caches",
        "eval",
        "Function",
    ]) {
        Object.defineProperty(self, capability, {
            value: denyNetworkAccess,
            configurable: false,
            writable: false,
        })
    }
    networkDisabled = true
}

function runtime(): Promise<PythonRuntime> {
    runtimePromise ??= import(/* @vite-ignore */ PYODIDE_MODULE_URL)
        .then((module) =>
            (module as PyodideModule).loadPyodide({
                indexURL: "/pyodide/",
            })
        )
        .catch((error) => {
            runtimePromise = undefined
            throw error
        })
    return runtimePromise
}

self.onmessage = async (event: MessageEvent<RunRequest>) => {
    const { id, source } = event.data
    try {
        const python = await runtime()
        disableNetworkAccess()
        self.postMessage({ id, started: true } satisfies RunResponse)
        const lines: string[] = []
        python.setStdout({ batched: (line) => lines.push(line) })
        python.setStderr({ batched: (line) => lines.push(line) })
        const value = await python.runPythonAsync(source)
        if (value !== undefined) {
            lines.push(String(value))
            if (typeof value === "object" && value !== null) {
                const disposable = value as { destroy?: unknown }
                if (typeof disposable.destroy === "function") {
                    disposable.destroy()
                }
            }
        }
        self.postMessage({ id, output: lines.join("\n") } satisfies RunResponse)
    } catch (error) {
        self.postMessage({
            id,
            error: error instanceof Error ? error.message : String(error),
        } satisfies RunResponse)
    }
}

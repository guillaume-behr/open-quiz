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
    fatal?: boolean
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
const MAX_OUTPUT_CHARACTERS = 1_000_000
let runtimePromise: Promise<PythonRuntime> | undefined
let networkDisabled = false

class OutputLimitError extends Error {}

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
    let outputLimitExceeded = false
    try {
        const python = await runtime()
        disableNetworkAccess()
        self.postMessage({ id, started: true } satisfies RunResponse)
        const lines: string[] = []
        let outputCharacters = 0
        const appendOutput = (line: string) => {
            outputCharacters += line.length + (lines.length ? 1 : 0)
            if (outputCharacters > MAX_OUTPUT_CHARACTERS) {
                outputLimitExceeded = true
                throw new OutputLimitError(
                    "Python output exceeded 1,000,000 characters."
                )
            }
            lines.push(line)
        }
        python.setStdout({ batched: appendOutput })
        python.setStderr({ batched: appendOutput })
        const value = await python.runPythonAsync(source)
        if (value !== undefined) {
            appendOutput(String(value))
            if (typeof value === "object" && value !== null) {
                const disposable = value as { destroy?: unknown }
                if (typeof disposable.destroy === "function") {
                    disposable.destroy()
                }
            }
        }
        self.postMessage({ id, output: lines.join("\n") } satisfies RunResponse)
    } catch (error) {
        const fatal = outputLimitExceeded || error instanceof OutputLimitError
        self.postMessage({
            id,
            error: error instanceof Error ? error.message : String(error),
            fatal,
        } satisfies RunResponse)
        if (fatal) self.close()
    }
}

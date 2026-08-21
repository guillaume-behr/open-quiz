/// <reference lib="webworker" />

import { loadPyodide } from "pyodide"

type RunRequest = {
    id: string
    source: string
}

type RunResponse = {
    id: string
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

const MAX_OUTPUT_CHARACTERS = 1_000_000
let runtimePromise: Promise<PythonRuntime> | undefined
let sandboxRestricted = false
let executionQueue = Promise.resolve()
const sendMessage = self.postMessage.bind(self)

class OutputLimitError extends Error {}

function denySandboxCapability(): never {
    throw new Error("This browser capability is disabled for Python execution.")
}

function restrictSandboxCapabilities() {
    if (sandboxRestricted) return
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
        "BroadcastChannel",
        "caches",
        "indexedDB",
    ]) {
        Object.defineProperty(self, capability, {
            value: denySandboxCapability,
            configurable: false,
            writable: false,
        })
    }
    sandboxRestricted = true
}

function runtime(): Promise<PythonRuntime> {
    runtimePromise ??= loadPyodide({ indexURL: "/pyodide/" }).catch((error) => {
        runtimePromise = undefined
        throw error
    })
    return runtimePromise
}

async function execute({ id, source }: RunRequest): Promise<void> {
    let outputLimitExceeded = false
    try {
        const python = await runtime()
        restrictSandboxCapabilities()
        sendMessage({ id, started: true } satisfies RunResponse)
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
        sendMessage({ id, output: lines.join("\n") } satisfies RunResponse)
    } catch (error) {
        const fatal = outputLimitExceeded || error instanceof OutputLimitError
        sendMessage({
            id,
            error: error instanceof Error ? error.message : String(error),
            fatal,
        } satisfies RunResponse)
        if (fatal) self.close()
    }
}

self.onmessage = (event: MessageEvent<RunRequest>) => {
    // Pyodide has one process-wide stdout/stderr configuration. Running two
    // snippets at once lets the later request replace the earlier callbacks,
    // mixing or losing output. Keep the public API concurrent while executing
    // requests in arrival order inside the shared runtime.
    executionQueue = executionQueue.then(() => execute(event.data))
}

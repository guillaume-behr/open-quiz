/// <reference lib="webworker" />

import type { loadPyodide as LoadPyodide } from "pyodide"

// The loader is served from /pyodide/<version>/ with the rest of the runtime
// (scripts/copy-pyodide.mjs) rather than bundled: its Node.js code paths
// would otherwise pull node: built-ins into the browser build. The version
// in the path lets the files be cached for good.
const PYODIDE_URL = `/pyodide/${__PYODIDE_VERSION__}/`

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
    outputLimitExceeded?: boolean
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

// Network, storage and worker APIs Python must not reach through Pyodide's
// `js` module.
const DENIED_GLOBALS = [
    "fetch",
    "XMLHttpRequest",
    "WebSocket",
    "WebSocketStream",
    "EventSource",
    "WebTransport",
    "RTCPeerConnection",
    "Worker",
    "SharedWorker",
    "importScripts",
    "BroadcastChannel",
    "caches",
    "indexedDB",
]

const DENIED_NAVIGATOR_PROPERTIES = [
    "storage",
    "locks",
    "serviceWorker",
    "usb",
    "hid",
    "serial",
    "bluetooth",
]

/**
 * Replaces a capability wherever it is defined, on the object and along its
 * prototype chain. Shadowing it on the object alone is not enough: `fetch`,
 * `importScripts` and `indexedDB` live on WorkerGlobalScope.prototype, where
 * `WorkerGlobalScope.prototype.fetch.call(self, url)` would still find them.
 */
function denyCapability(target: object, capability: string) {
    const denied = {
        value: denySandboxCapability,
        configurable: false,
        writable: false,
    }
    for (
        let owner: object | null = Object.getPrototypeOf(target);
        owner !== null && owner !== Object.prototype;
        owner = Object.getPrototypeOf(owner)
    ) {
        if (Object.hasOwn(owner, capability)) {
            Object.defineProperty(owner, capability, denied)
        }
    }
    Object.defineProperty(target, capability, denied)
}

function restrictSandboxCapabilities() {
    if (sandboxRestricted) return
    for (const capability of DENIED_GLOBALS) {
        denyCapability(self, capability)
    }
    for (const property of DENIED_NAVIGATOR_PROPERTIES) {
        denyCapability(self.navigator, property)
    }
    sandboxRestricted = true
}

async function loadRuntime(): Promise<PythonRuntime> {
    const { loadPyodide } = (await import(
        /* @vite-ignore */ `${PYODIDE_URL}pyodide.mjs`
    )) as { loadPyodide: typeof LoadPyodide }
    return loadPyodide({ indexURL: PYODIDE_URL })
}

function runtime(): Promise<PythonRuntime> {
    runtimePromise ??= loadRuntime().catch((error: unknown) => {
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
            outputLimitExceeded: fatal,
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

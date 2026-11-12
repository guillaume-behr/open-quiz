// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
    describePythonFailure,
    nextRequestId,
    PythonRunnerError,
    runPython,
} from "./python-runner"
import { first } from "@/test/first"

type Reply = {
    id: string
    started?: boolean
    output?: string
    error?: string
    fatal?: boolean
    outputLimitExceeded?: boolean
}

class FakeWorker {
    static instances: FakeWorker[] = []
    onmessage: ((event: MessageEvent<Reply>) => void) | null = null
    onerror: (() => void) | null = null
    posted: { id: string; source: string }[] = []
    terminated = false
    constructor() {
        FakeWorker.instances.push(this)
    }
    postMessage(message: { id: string; source: string }) {
        this.posted.push(message)
    }
    terminate() {
        this.terminated = true
    }
    reply(data: Reply) {
        this.onmessage?.({ data } as MessageEvent<Reply>)
    }
}

function current(): FakeWorker {
    const worker = FakeWorker.instances.at(-1)
    if (!worker) throw new Error("no worker")
    return worker
}

function lastId(): string {
    return current().posted.at(-1)?.id ?? ""
}

describe("runPython", () => {
    beforeEach(() => {
        vi.useFakeTimers()
        vi.stubGlobal("Worker", FakeWorker)
    })
    afterEach(() => {
        // Leave no worker behind for the next test.
        current().onerror?.()
        vi.useRealTimers()
    })

    it("returns the program's output and reuses the worker", async () => {
        const first = runPython("print(1)")
        current().reply({ id: lastId(), started: true })
        current().reply({ id: lastId(), started: true })
        current().reply({ id: lastId(), output: "1\n" })
        await expect(first).resolves.toBe("1\n")
        const second = runPython("pass")
        current().reply({ id: "unknown", output: "ignored" })
        current().reply({ id: lastId() })
        await expect(second).resolves.toBe("")
        expect(FakeWorker.instances).toHaveLength(1)
    })

    it("reports program errors, output limits and fatal errors", async () => {
        const traceback = runPython("1/0")
        current().reply({ id: lastId(), error: "ZeroDivisionError" })
        await expect(traceback).rejects.toThrow("ZeroDivisionError")

        const noisy = runPython("print('x' * 10**9)")
        current().reply({ id: lastId(), error: "", outputLimitExceeded: true })
        await expect(noisy).rejects.toMatchObject({ reason: "output-too-long" })

        const worker = current()
        const fatal = runPython("boom")
        const other = runPython("pass")
        worker.reply({ id: first(worker.posted).id, error: "x" })
        worker.reply({
            id: worker.posted.at(-2)?.id ?? "",
            error: "dead",
            fatal: true,
        })
        await expect(fatal).rejects.toThrow("dead")
        await expect(other).rejects.toThrow("dead")
        expect(worker.terminated).toBe(true)
    })

    it("stops a run that does not start or does not finish in time", async () => {
        const neverStarts = runPython("pass")
        vi.advanceTimersByTime(60_000)
        await expect(neverStarts).rejects.toMatchObject({
            reason: "init-timeout",
        })

        const endless = runPython("while True: pass")
        current().reply({ id: lastId(), started: true })
        vi.advanceTimersByTime(10_000)
        await expect(endless).rejects.toMatchObject({ reason: "timeout" })
    })

    it("fails a crashed worker and an oversized source", async () => {
        const crashed = runPython("pass")
        current().onerror?.()
        await expect(crashed).rejects.toMatchObject({ reason: "crashed" })
        await expect(runPython("x".repeat(20_001))).rejects.toMatchObject({
            reason: "source-too-long",
        })
    })
})

describe("describePythonFailure", () => {
    const t = (key: string) => `translated:${key}`

    it("translates a failure of the runner itself", () => {
        expect(describePythonFailure(new PythonRunnerError("timeout"), t)).toBe(
            "translated:python-error-timeout"
        )
        expect(
            describePythonFailure(new PythonRunnerError("output-too-long"), t)
        ).toBe("translated:python-error-output-too-long")
    })

    it("shows the program's own error as Python wrote it", () => {
        expect(describePythonFailure(new Error("NameError: name 'x'"), t)).toBe(
            "NameError: name 'x'"
        )
        expect(describePythonFailure("boom", t)).toBe("boom")
    })
})

describe("nextRequestId", () => {
    it("works outside a secure context, where crypto.randomUUID is missing", () => {
        // Plain HTTP on a LAN address: the browser hides randomUUID.
        vi.stubGlobal("crypto", {})
        const first = nextRequestId()
        const second = nextRequestId()
        expect(first).not.toBe(second)
    })
})

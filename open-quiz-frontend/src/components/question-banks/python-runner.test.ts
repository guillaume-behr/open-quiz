import { afterEach, describe, expect, it, vi } from "vitest"

import {
    describePythonFailure,
    nextRequestId,
    PythonRunnerError,
} from "./python-runner"

const t = (key: string) => `translated:${key}`

describe("describePythonFailure", () => {
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
    afterEach(() => {
        vi.unstubAllGlobals()
    })

    it("works outside a secure context, where crypto.randomUUID is missing", () => {
        // Plain HTTP on a LAN address: the browser hides randomUUID.
        vi.stubGlobal("crypto", {})
        const first = nextRequestId()
        const second = nextRequestId()
        expect(first).not.toBe(second)
    })
})

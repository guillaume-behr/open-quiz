import { describe, expect, it } from "vitest"

import { describePythonFailure, PythonRunnerError } from "./python-runner"

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

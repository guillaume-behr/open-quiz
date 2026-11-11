import { describe, expect, it } from "vitest"

import * as patterns from "./input-patterns"

// Browsers compile the pattern attribute as ^(?:pattern)$ with the v flag and
// silently ignore a pattern that does not compile.
function compile(pattern: string): RegExp {
    return new RegExp(`^(?:${pattern})$`, "v")
}

describe("input patterns", () => {
    it.each(Object.entries(patterns))("%s compiles with the v flag", (_, p) => {
        expect(() => compile(p)).not.toThrow()
    })

    it("accepts the identifiers the API accepts", () => {
        const username = compile(patterns.USERNAME_PATTERN)
        expect(username.test("jean.dupont_2-b")).toBe(true)
        expect(username.test("jean dupont")).toBe(false)
        expect(username.test("élève")).toBe(false)
    })

    it("accepts six-digit two-factor codes only", () => {
        const code = compile(patterns.TWO_FACTOR_CODE_PATTERN)
        expect(code.test("012345")).toBe(true)
        expect(code.test("12345a")).toBe(false)
    })
})

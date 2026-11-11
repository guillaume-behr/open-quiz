import { describe, expect, it } from "vitest"

import { formatMinutes, formatPercent } from "./locale"

describe("formatMinutes", () => {
    it("formats a duration in whole minutes for the locale", () => {
        expect(formatMinutes(1800, "en")).toBe("30 min")
        expect(formatMinutes(90, "de")).toBe("2 Min.")
    })
})

describe("formatPercent", () => {
    it("formats a percentage for the locale", () => {
        expect(formatPercent(50, "en")).toBe("50%")
        // French puts a (non-breaking) space before the sign.
        expect(formatPercent(50, "fr")).toMatch(/^50\s%$/)
    })
})

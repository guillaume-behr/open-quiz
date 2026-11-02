import { describe, expect, it } from "vitest"

import { formatScore, GRADE_SCALE, gradeOnScale } from "@/lib/grades"

describe("gradeOnScale", () => {
    it("rebases a score on the grade scale", () => {
        expect(GRADE_SCALE).toBe(20)
        expect(gradeOnScale(7.5, 15)).toBe(10)
        expect(gradeOnScale(3, 3)).toBe(20)
        expect(gradeOnScale(0, 8)).toBe(0)
    })

    it("has no grade for a paper without points", () => {
        expect(gradeOnScale(0, 0)).toBeNull()
        expect(gradeOnScale(2, -1)).toBeNull()
    })

    it("refuses non-finite values instead of showing NaN", () => {
        expect(gradeOnScale(Number.NaN, 10)).toBeNull()
        expect(gradeOnScale(5, Number.POSITIVE_INFINITY)).toBeNull()
    })
})

describe("formatScore", () => {
    it("keeps at most two decimals in the reader's locale", () => {
        expect(formatScore(12.3456, "en")).toBe("12.35")
        expect(formatScore(12.3456, "fr")).toBe("12,35")
        expect(formatScore(14, "fr")).toBe("14")
    })
})

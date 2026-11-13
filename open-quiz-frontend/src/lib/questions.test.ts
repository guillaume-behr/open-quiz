import { describe, expect, it } from "vitest"

import type { Question } from "@/api/types"
import { questionMaxPoints } from "@/lib/questions"

function withPoints(...points: number[]): Pick<Question, "choices"> {
    return {
        choices: points.map((value) => ({ points: value })),
    } as Pick<Question, "choices">
}

describe("questionMaxPoints", () => {
    it("adds the points of the choices and ignores penalties", () => {
        expect(questionMaxPoints(withPoints(1, 2.5, -1))).toBe(3.5)
    })

    it("is zero without choices", () => {
        expect(questionMaxPoints(withPoints())).toBe(0)
    })
})

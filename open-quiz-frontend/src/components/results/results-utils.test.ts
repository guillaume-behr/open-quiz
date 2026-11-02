import { describe, expect, it } from "vitest"

import { resultStart } from "@/components/results/results-utils"

describe("resultStart", () => {
    it("dates a result by its start, or its creation before it started", () => {
        expect(
            resultStart({
                started_at: "2026-03-02T08:00:00Z",
                created_at: "2026-03-01T08:00:00Z",
            }).toISOString()
        ).toBe("2026-03-02T08:00:00.000Z")
        expect(
            resultStart({
                started_at: null,
                created_at: "2026-03-01T08:00:00Z",
            }).toISOString()
        ).toBe("2026-03-01T08:00:00.000Z")
    })
})

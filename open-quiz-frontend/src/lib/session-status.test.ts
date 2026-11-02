import { describe, expect, it } from "vitest"

import { isActiveSessionStatus } from "@/lib/session-status"

describe("isActiveSessionStatus", () => {
    it("treats waiting, running and paused sessions as active", () => {
        expect(isActiveSessionStatus("waiting")).toBe(true)
        expect(isActiveSessionStatus("in_progress")).toBe(true)
        expect(isActiveSessionStatus("paused")).toBe(true)
    })

    it("treats ended or unknown sessions as inactive", () => {
        expect(isActiveSessionStatus("finished")).toBe(false)
        expect(isActiveSessionStatus("cancelled")).toBe(false)
        expect(isActiveSessionStatus(null)).toBe(false)
        expect(isActiveSessionStatus(undefined)).toBe(false)
    })
})

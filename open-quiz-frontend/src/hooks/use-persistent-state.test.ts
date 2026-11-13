// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { usePersistentState } from "@/hooks/use-persistent-state"

const KEY = "test-view"
const VIEWS = ["cards", "schedule"] as const

describe("usePersistentState", () => {
    afterEach(() => {
        localStorage.clear()
        vi.restoreAllMocks()
    })

    it("starts from the stored choice and stores each change", () => {
        localStorage.setItem(KEY, "schedule")
        const { result } = renderHook(() =>
            usePersistentState(KEY, VIEWS, "cards")
        )
        expect(result.current[0]).toBe("schedule")
        act(() => result.current[1]("cards"))
        expect(result.current[0]).toBe("cards")
        expect(localStorage.getItem(KEY)).toBe("cards")
    })

    it("falls back on an unknown value or unavailable storage", () => {
        localStorage.setItem(KEY, "list")
        const unknown = renderHook(() =>
            usePersistentState(KEY, VIEWS, "cards")
        )
        expect(unknown.result.current[0]).toBe("cards")

        vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
            throw new Error("denied")
        })
        vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
            throw new Error("denied")
        })
        const blocked = renderHook(() =>
            usePersistentState(KEY, VIEWS, "schedule")
        )
        expect(blocked.result.current[0]).toBe("schedule")
        act(() => blocked.result.current[1]("cards"))
        expect(blocked.result.current[0]).toBe("cards")
    })
})

// @vitest-environment jsdom
import { act, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { useAsyncAction } from "./use-async-action"

describe("useAsyncAction", () => {
    it("tracks a running action and the message of its failure", async () => {
        let finish: () => void = () => undefined
        let fail = false
        const { result } = renderHook(() =>
            useAsyncAction(
                (value: number) =>
                    fail
                        ? Promise.reject(new Error(`bad ${value}`))
                        : new Promise<void>((resolve) => (finish = resolve)),
                (caught) => (caught as Error).message
            )
        )
        let running: Promise<void> = Promise.resolve()
        act(() => {
            running = result.current.run(1)
        })
        expect(result.current.isPending).toBe(true)
        await act(async () => {
            finish()
            await running
        })
        expect(result.current.isPending).toBe(false)
        expect(result.current.error).toBeNull()

        fail = true
        await act(() => result.current.run(2))
        expect(result.current.error).toBe("bad 2")
        act(() => result.current.setError(null))
        expect(result.current.error).toBeNull()
    })
})

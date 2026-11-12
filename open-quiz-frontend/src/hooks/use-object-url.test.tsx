// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import { useObjectUrl } from "./use-object-url"

function stubObjectUrls() {
    let next = 0
    const create = vi.fn(() => `blob:${++next}`)
    const revoke = vi.fn()
    vi.stubGlobal("URL", { createObjectURL: create, revokeObjectURL: revoke })
    return { create, revoke }
}

describe("useObjectUrl", () => {
    it("revokes the URL when the loader changes and on unmount", async () => {
        const { revoke } = stubObjectUrls()
        const first = () => Promise.resolve(new Blob(["a"]))
        const second = () => Promise.resolve(new Blob(["b"]))
        const { result, rerender, unmount } = renderHook(
            ({ load }) => useObjectUrl(load),
            { initialProps: { load: first } }
        )
        await waitFor(() => expect(result.current).toBe("blob:1"))
        rerender({ load: second })
        expect(result.current).toBeNull()
        expect(revoke).toHaveBeenCalledWith("blob:1")
        await waitFor(() => expect(result.current).toBe("blob:2"))
        unmount()
        expect(revoke).toHaveBeenCalledWith("blob:2")
    })

    it("revokes a blob that arrives after unmount and clears on failure", async () => {
        const { revoke } = stubObjectUrls()
        let deliver: (blob: Blob) => void = () => undefined
        const late = () => new Promise<Blob>((resolve) => (deliver = resolve))
        const { unmount } = renderHook(() => useObjectUrl(late))
        unmount()
        deliver(new Blob(["late"]))
        await waitFor(() => expect(revoke).toHaveBeenCalledWith("blob:1"))

        const failing = () => Promise.reject(new Error("gone"))
        const { result } = renderHook(() => useObjectUrl(failing))
        await waitFor(() => expect(result.current).toBeNull())
    })
})

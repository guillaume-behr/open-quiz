// @vitest-environment jsdom
import { act, render } from "@testing-library/react"
import {
    NavigationType,
    createMemoryRouter,
    RouterProvider,
} from "react-router"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { shouldMoveFocus } from "@/components/navigation/route-focus"
import { RouteFocusManager } from "@/components/navigation/route-focus-manager"

describe("shouldMoveFocus", () => {
    it("moves focus when a push leads to another pathname", () => {
        expect(shouldMoveFocus("/a", "/b", NavigationType.Push)).toBe(true)
        expect(shouldMoveFocus("/a", "/b", NavigationType.Pop)).toBe(true)
    })

    it("keeps focus on replace and state-only navigations", () => {
        expect(shouldMoveFocus("/a", "/b", NavigationType.Replace)).toBe(false)
        expect(shouldMoveFocus("/a", "/a", NavigationType.Push)).toBe(false)
    })
})

describe("RouteFocusManager", () => {
    beforeEach(() => {
        vi.stubGlobal(
            "requestAnimationFrame",
            (callback: FrameRequestCallback) => {
                callback(0)
                return 0
            }
        )
    })

    afterEach(() => {
        vi.unstubAllGlobals()
    })

    function Page() {
        return (
            <>
                <RouteFocusManager />
                <main id="contenu" tabIndex={-1} />
                <button type="button">elsewhere</button>
            </>
        )
    }

    it("focuses the main content only after a push to another screen", async () => {
        const router = createMemoryRouter(
            [
                { path: "/a", element: <Page /> },
                { path: "/b", element: <Page /> },
            ],
            { initialEntries: ["/a"] }
        )
        const { getByRole } = render(<RouterProvider router={router} />)
        const button = getByRole("button")

        button.focus()
        await act(() => router.navigate("/b", { replace: true }))
        expect(document.activeElement).toBe(getByRole("button"))

        await act(() => router.navigate("/a"))
        expect(document.activeElement?.id).toBe("contenu")
    })
})

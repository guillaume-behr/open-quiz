// @vitest-environment jsdom
import { act, createElement } from "react"
import { createRoot, type Root } from "react-dom/client"
import {
    MemoryRouter,
    Route,
    Routes,
    useNavigate,
    type NavigateFunction,
} from "react-router"
import { afterEach, expect, it, vi } from "vitest"

import { RouteErrorBoundary } from "./error-boundary"

// React warns unless the environment says it supports act().
;(
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true

let root: Root | null = null

afterEach(() => {
    act(() => root?.unmount())
    root = null
    vi.restoreAllMocks()
})

function Broken(): never {
    throw new Error("render failure")
}

it("clears an error shown on one route when navigating to another", () => {
    // React and the boundary both report the caught error.
    vi.spyOn(console, "error").mockImplementation(() => {})
    let navigate: NavigateFunction | null = null
    function Navigator() {
        navigate = useNavigate()
        return null
    }
    const container = document.createElement("div")
    root = createRoot(container)
    act(() =>
        root?.render(
            createElement(
                MemoryRouter,
                { initialEntries: ["/broken"] },
                createElement(Navigator),
                createElement(
                    RouteErrorBoundary,
                    null,
                    createElement(
                        Routes,
                        null,
                        createElement(Route, {
                            path: "/broken",
                            element: createElement(Broken),
                        }),
                        createElement(Route, {
                            path: "/fine",
                            element: "Fine page",
                        })
                    )
                )
            )
        )
    )
    expect(container.textContent).toContain("error-page-title")

    act(() => void navigate?.("/fine"))

    expect(container.textContent).toContain("Fine page")
    expect(container.textContent).not.toContain("error-page-title")
})

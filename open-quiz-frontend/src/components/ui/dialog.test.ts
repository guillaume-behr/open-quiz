// @vitest-environment jsdom
import { act, createElement } from "react"
import { createRoot } from "react-dom/client"
import { describe, expect, it, vi } from "vitest"

// Each run of the Dialog component calls useTranslation once.
const translationCalls = vi.hoisted(() => ({ count: 0 }))
vi.mock("react-i18next", () => ({
    useTranslation: () => {
        translationCalls.count += 1
        return { t: (key: string) => key }
    },
}))

import { Dialog } from "./dialog"

// React warns unless the environment says it supports act().
;(
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true

function renderDialog(label: string) {
    return createElement(Dialog, {
        open: true,
        onOpenChange: () => undefined,
        title: "Title",
        children: createElement("p", null, label),
    })
}

describe("Dialog", () => {
    it("renders once per parent render while open", () => {
        const container = document.createElement("div")
        document.body.append(container)
        const root = createRoot(container)
        act(() => root.render(renderDialog("first")))

        translationCalls.count = 0
        act(() => root.render(renderDialog("second")))

        expect(translationCalls.count).toBe(1)
        expect(document.body.textContent).toContain("second")
        act(() => root.unmount())
    })

    it("keeps showing its last content while it closes", () => {
        const container = document.createElement("div")
        document.body.append(container)
        const root = createRoot(container)
        act(() => root.render(renderDialog("shown while open")))
        act(() =>
            root.render(
                createElement(Dialog, {
                    open: false,
                    onOpenChange: () => undefined,
                    title: "Title",
                    children: createElement("p", null, "never shown"),
                })
            )
        )

        expect(document.body.textContent).not.toContain("never shown")
        act(() => root.unmount())
    })
})

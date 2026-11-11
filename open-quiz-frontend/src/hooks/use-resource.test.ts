// @vitest-environment jsdom
import { act, createElement } from "react"
import { createRoot } from "react-dom/client"
import { describe, expect, it } from "vitest"

import { useResource } from "./use-resource"

// React warns unless the environment says it supports act().
;(
    globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true

const signals: AbortSignal[] = []
// Never settles: the test only looks at what happens to the signals.
function loader(signal: AbortSignal): Promise<number> {
    signals.push(signal)
    return new Promise<number>(() => undefined)
}
const otherLoader = (signal: AbortSignal) => loader(signal)

function Probe({ load }: { load: (signal: AbortSignal) => Promise<number> }) {
    useResource(load)
    return null
}

describe("useResource", () => {
    it("aborts the request a newer load or an unmount supersedes", () => {
        const root = createRoot(document.createElement("div"))
        act(() => root.render(createElement(Probe, { load: loader })))
        expect(signals).toHaveLength(1)
        expect(signals[0]?.aborted).toBe(false)

        act(() => root.render(createElement(Probe, { load: otherLoader })))
        expect(signals).toHaveLength(2)
        expect(signals[0]?.aborted).toBe(true)
        expect(signals[1]?.aborted).toBe(false)

        act(() => root.unmount())
        expect(signals[1]?.aborted).toBe(true)
    })
})

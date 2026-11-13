// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest"

import { withPrintWindow } from "./print-window"

function fakeWindow() {
    const timers: (() => void)[] = []
    const printWindow = {
        opener: {},
        close: vi.fn(),
        focus: vi.fn(),
        print: vi.fn(),
        setTimeout: (callback: () => void) => timers.push(callback),
    }
    vi.spyOn(window, "open").mockReturnValue(printWindow as unknown as Window)
    return { printWindow, timers }
}

describe("withPrintWindow", () => {
    afterEach(() => {
        vi.restoreAllMocks()
    })

    it("opens the window at once, then prints what was written", async () => {
        const { printWindow, timers } = fakeWindow()
        const write = vi.fn(() => Promise.resolve())
        const printing = withPrintWindow(write)
        expect(window.open).toHaveBeenCalledWith("", "_blank")
        expect(printWindow.opener).toBeNull()
        await expect(printing).resolves.toBe(true)
        expect(write).toHaveBeenCalledWith(printWindow)
        expect(printWindow.focus).toHaveBeenCalled()
        expect(printWindow.print).not.toHaveBeenCalled()
        for (const timer of timers) timer()
        expect(printWindow.print).toHaveBeenCalled()
        expect(printWindow.close).not.toHaveBeenCalled()
    })

    it("closes the window when writing fails", async () => {
        const { printWindow } = fakeWindow()
        await expect(
            withPrintWindow(() => Promise.reject(new Error("boom")))
        ).rejects.toThrow("boom")
        expect(printWindow.close).toHaveBeenCalled()
        expect(printWindow.print).not.toHaveBeenCalled()
    })

    it("reports a blocked pop-up without writing", async () => {
        vi.spyOn(window, "open").mockReturnValue(null)
        const write = vi.fn()
        await expect(withPrintWindow(write)).resolves.toBe(false)
        expect(write).not.toHaveBeenCalled()
    })
})

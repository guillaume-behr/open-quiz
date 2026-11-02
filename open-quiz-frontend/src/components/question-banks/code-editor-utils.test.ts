// @vitest-environment jsdom
import type { KeyboardEvent } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { indentCode } from "@/components/question-banks/code-editor-utils"

function keydown(
    key: string,
    value: string,
    start: number,
    end = start
): {
    event: KeyboardEvent<HTMLTextAreaElement>
    textarea: HTMLTextAreaElement
} {
    const textarea = document.createElement("textarea")
    textarea.value = value
    textarea.setSelectionRange(start, end)
    const event = {
        key,
        currentTarget: textarea,
        preventDefault: vi.fn(),
    } as unknown as KeyboardEvent<HTMLTextAreaElement>
    return { event, textarea }
}

beforeEach(() => {
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
        callback(0)
        return 0
    })
})

afterEach(() => {
    vi.unstubAllGlobals()
})

describe("indentCode", () => {
    it("ignores every key but Tab", () => {
        const onChange = vi.fn()
        const { event } = keydown("Enter", "print(1)", 0)
        indentCode(event, "print(1)", onChange)
        expect(onChange).not.toHaveBeenCalled()
        expect(event.preventDefault).not.toHaveBeenCalled()
    })

    it("inserts a tab at the caret and moves past it", () => {
        const onChange = vi.fn()
        const value = "if x:\npass"
        const { event, textarea } = keydown("Tab", value, 6)
        indentCode(event, value, onChange)
        expect(event.preventDefault).toHaveBeenCalled()
        expect(onChange).toHaveBeenCalledWith("if x:\n\tpass")
        expect([textarea.selectionStart, textarea.selectionEnd]).toEqual([7, 7])
    })

    it("indents every selected line", () => {
        const onChange = vi.fn()
        const value = "a\nb\nc"
        const { event } = keydown("Tab", value, 2, 5)
        indentCode(event, value, onChange)
        expect(onChange).toHaveBeenCalledWith("a\n\tb\n\tc")
    })
})

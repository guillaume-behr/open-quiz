// @vitest-environment jsdom
import type { KeyboardEvent } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { indentCode } from "@/components/question-banks/code-editor-utils"

function keydown(
    key: string,
    value: string,
    start: number,
    end = start,
    {
        shiftKey = false,
        textarea = document.createElement("textarea"),
    }: { shiftKey?: boolean; textarea?: HTMLTextAreaElement } = {}
): {
    event: KeyboardEvent<HTMLTextAreaElement>
    textarea: HTMLTextAreaElement
} {
    textarea.value = value
    textarea.setSelectionRange(start, end)
    const event = {
        key,
        shiftKey,
        currentTarget: textarea,
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
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

    it("leaves the line after a selection of whole lines untouched", () => {
        const value = "a\nb\nc"
        // "a\nb\n" selected, as dragging or shift+down over two lines does.
        const { event, textarea } = keydown("Tab", value, 0, 4)
        const onChange = vi.fn((next: string) => {
            textarea.value = next
        })
        indentCode(event, value, onChange)
        expect(onChange).toHaveBeenCalledWith("\ta\n\tb\nc")
        expect([textarea.selectionStart, textarea.selectionEnd]).toEqual([1, 6])
    })

    it("outdents the current line with Shift+Tab", () => {
        const value = "if x:\n\tpass"
        const { event, textarea } = keydown("Tab", value, 8, 8, {
            shiftKey: true,
        })
        const onChange = vi.fn()
        indentCode(event, value, onChange)
        expect(event.preventDefault).toHaveBeenCalled()
        expect(onChange).toHaveBeenCalledWith("if x:\npass")
        expect([textarea.selectionStart, textarea.selectionEnd]).toEqual([7, 7])
    })

    it("outdents every selected line by a tab or up to four spaces", () => {
        const value = "a\n    b\n  c\nd"
        const { event, textarea } = keydown("Tab", value, 2, 12, {
            shiftKey: true,
        })
        const onChange = vi.fn()
        indentCode(event, value, onChange)
        expect(onChange).toHaveBeenCalledWith("a\nb\nc\nd")
        expect([textarea.selectionStart, textarea.selectionEnd]).toEqual([2, 6])
    })

    it("leaves unindented code as it is on Shift+Tab", () => {
        const value = "print(1)"
        const { event } = keydown("Tab", value, 3, 3, { shiftKey: true })
        const onChange = vi.fn()
        indentCode(event, value, onChange)
        expect(event.preventDefault).toHaveBeenCalled()
        expect(onChange).not.toHaveBeenCalled()
    })

    it("lets Tab and Shift+Tab leave the editor after Escape", () => {
        const onChange = vi.fn()
        const textarea = document.createElement("textarea")
        const escape = keydown("Escape", "x", 1, 1, { textarea })
        indentCode(escape.event, "x", onChange)
        expect(escape.event.stopPropagation).toHaveBeenCalled()

        const shift = keydown("Shift", "x", 1, 1, { textarea })
        indentCode(shift.event, "x", onChange)
        const tab = keydown("Tab", "x", 1, 1, { textarea, shiftKey: true })
        indentCode(tab.event, "x", onChange)
        expect(tab.event.preventDefault).not.toHaveBeenCalled()
        expect(onChange).not.toHaveBeenCalled()

        // Only the next Tab is released.
        const nextTab = keydown("Tab", "x", 1, 1, { textarea })
        indentCode(nextTab.event, "x", onChange)
        expect(nextTab.event.preventDefault).toHaveBeenCalled()
        expect(onChange).toHaveBeenCalledWith("x\t")
    })

    it("lets a second Escape through and traps Tab again after typing", () => {
        const onChange = vi.fn()
        const textarea = document.createElement("textarea")
        indentCode(
            keydown("Escape", "x", 1, 1, { textarea }).event,
            "x",
            onChange
        )
        const second = keydown("Escape", "x", 1, 1, { textarea })
        indentCode(second.event, "x", onChange)
        expect(second.event.stopPropagation).not.toHaveBeenCalled()

        indentCode(keydown("a", "x", 1, 1, { textarea }).event, "x", onChange)
        const tab = keydown("Tab", "x", 1, 1, { textarea })
        indentCode(tab.event, "x", onChange)
        expect(tab.event.preventDefault).toHaveBeenCalled()
    })
})

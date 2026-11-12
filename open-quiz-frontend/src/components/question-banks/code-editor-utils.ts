import type { KeyboardEvent } from "react"

// Editors whose next Tab press leaves them instead of indenting: Escape
// releases the Tab key so keyboard users are never trapped (WCAG 2.1.2).
const releasedEditors = new WeakSet<HTMLTextAreaElement>()

const MODIFIER_KEYS = new Set(["Shift", "Control", "Alt", "Meta"])

// One indentation level removed by Shift+Tab: a tab or up to four spaces.
const LEADING_INDENT = /^(\t| {1,4})/

export function indentCode(
    event: KeyboardEvent<HTMLTextAreaElement>,
    value: string,
    onChange: (value: string) => void
): void {
    const textarea = event.currentTarget

    if (event.key === "Escape") {
        // A second Escape goes on as usual, e.g. to close a dialog.
        if (releasedEditors.has(textarea)) return
        releasedEditors.add(textarea)
        event.stopPropagation()
        return
    }

    if (event.key !== "Tab") {
        if (!MODIFIER_KEYS.has(event.key)) releasedEditors.delete(textarea)
        return
    }

    if (releasedEditors.has(textarea)) {
        // Let the browser move focus out of the editor.
        releasedEditors.delete(textarea)
        return
    }

    event.preventDefault()
    if (event.shiftKey) {
        outdentCode(textarea, value, onChange)
        return
    }

    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const lineStart = value.lastIndexOf("\n", start - 1) + 1

    if (start !== end) {
        const blockEnd = selectedBlockEnd(value, lineStart, end)
        const selectedCode = value.slice(lineStart, blockEnd)
        const indentedCode = selectedCode.replace(/^/gm, "\t")
        onChange(
            value.slice(0, lineStart) + indentedCode + value.slice(blockEnd)
        )
        requestAnimationFrame(() => {
            textarea.setSelectionRange(
                start + 1,
                end + (indentedCode.length - selectedCode.length)
            )
        })
        return
    }

    onChange(value.slice(0, start) + "\t" + value.slice(end))
    requestAnimationFrame(() => {
        textarea.setSelectionRange(start + 1, start + 1)
    })
}

// A selection of whole lines usually ends just after a line break; the line
// that follows it is not selected and must stay as it is.
function selectedBlockEnd(value: string, lineStart: number, end: number) {
    return end - 1 >= lineStart && value[end - 1] === "\n" ? end - 1 : end
}

function outdentCode(
    textarea: HTMLTextAreaElement,
    value: string,
    onChange: (value: string) => void
): void {
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const lineStart = value.lastIndexOf("\n", start - 1) + 1
    let blockEnd: number
    if (start !== end) {
        blockEnd = selectedBlockEnd(value, lineStart, end)
    } else {
        const lineEnd = value.indexOf("\n", start)
        blockEnd = lineEnd === -1 ? value.length : lineEnd
    }

    let firstLineRemoved = 0
    let removed = 0
    const outdentedCode = value
        .slice(lineStart, blockEnd)
        .split("\n")
        .map((line, index) => {
            const indent = LEADING_INDENT.exec(line)?.[0].length ?? 0
            if (index === 0) firstLineRemoved = indent
            removed += indent
            return line.slice(indent)
        })
        .join("\n")
    if (removed === 0) return

    onChange(value.slice(0, lineStart) + outdentedCode + value.slice(blockEnd))
    const nextStart = start - Math.min(firstLineRemoved, start - lineStart)
    const nextEnd =
        start === end ? nextStart : Math.max(nextStart, end - removed)
    requestAnimationFrame(() => {
        textarea.setSelectionRange(nextStart, nextEnd)
    })
}

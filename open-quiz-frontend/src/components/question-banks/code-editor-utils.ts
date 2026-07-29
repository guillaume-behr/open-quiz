import type { KeyboardEvent } from "react"

export function indentCode(
    event: KeyboardEvent<HTMLTextAreaElement>,
    value: string,
    onChange: (value: string) => void
): void {
    if (event.key !== "Tab") return

    event.preventDefault()
    const textarea = event.currentTarget
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const lineStart = value.lastIndexOf("\n", start - 1) + 1

    if (start !== end) {
        const selectedCode = value.slice(lineStart, end)
        const indentedCode = selectedCode.replace(/^/gm, "\t")
        onChange(value.slice(0, lineStart) + indentedCode + value.slice(end))
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

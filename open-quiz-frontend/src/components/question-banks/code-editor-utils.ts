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
        // A selection of whole lines usually ends just after a line break;
        // the line that follows it is not selected and must stay as it is.
        const blockEnd =
            end - 1 >= lineStart && value[end - 1] === "\n" ? end - 1 : end
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

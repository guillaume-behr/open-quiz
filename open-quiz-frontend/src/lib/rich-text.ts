/**
 * Light formatting for question prompts.
 *
 * Prompts stay plain text in the database. A small Markdown-like subset gives
 * teachers emphasis without any HTML ever reaching the page:
 *
 * - `**gras**` for bold;
 * - `*italique*` for italic;
 * - `` `code` `` for inline code;
 * - line breaks are kept as typed;
 * - a backslash shows a marker literally: `\*`, `` \` ``, `\\`.
 *
 * A marker only opens when a non-space character follows it and only closes
 * after a non-space character, so `2 * 3 * 4` stays as typed.
 */

export type RichTextNode =
    | { type: "text"; text: string }
    | { type: "code"; text: string }
    | { type: "bold" | "italic"; children: RichTextNode[] }

const ESCAPABLE = new Set(["*", "`", "\\"])

function isSpace(character: string | undefined) {
    return character === undefined || /\s/.test(character)
}

/** Index just after a closing backtick, or -1 when the span never closes. */
function codeSpanEnd(source: string, start: number) {
    const close = source.indexOf("`", start + 1)
    return close > start + 1 ? close + 1 : -1
}

function starRunLength(source: string, start: number) {
    let end = start
    while (source[end] === "*") end += 1
    return end - start
}

/**
 * Index of the closing `marker` for an emphasis whose content starts at
 * `from`, or -1. Code spans and escapes are skipped, and a bold run inside an
 * italic one (or the reverse) is stepped over so it cannot close the outer.
 * In a shared run such as `***`, the inner emphasis closes on the stars next
 * to its text and the outer one on the last stars.
 */
function findClosing(
    source: string,
    from: number,
    marker: "*" | "**",
    nested = false
): number {
    let index = from
    while (index < source.length) {
        const character = source[index]
        if (character === "\\" && ESCAPABLE.has(source[index + 1] ?? "")) {
            index += 2
            continue
        }
        if (character === "`") {
            const end = codeSpanEnd(source, index)
            if (end !== -1) {
                index = end
                continue
            }
        }
        if (character !== "*") {
            index += 1
            continue
        }
        const run = starRunLength(source, index)
        const canClose = index > from && !isSpace(source[index - 1])
        const closes = marker === "**" ? run >= 2 : run % 2 === 1
        if (canClose && closes)
            return nested ? index : index + run - marker.length
        const innerMarker = run >= 2 ? "**" : "*"
        if (innerMarker !== marker && !isSpace(source[index + run])) {
            const innerStart = index + innerMarker.length
            const innerClose = findClosing(
                source,
                innerStart,
                innerMarker,
                true
            )
            if (innerClose !== -1) {
                index = innerClose + innerMarker.length
                continue
            }
        }
        index += run
    }
    return -1
}

export function parseRichText(source: string): RichTextNode[] {
    const nodes: RichTextNode[] = []
    let text = ""

    function flushText() {
        if (text) nodes.push({ type: "text", text })
        text = ""
    }

    let index = 0
    while (index < source.length) {
        const character = source[index]
        if (character === "\\" && ESCAPABLE.has(source[index + 1] ?? "")) {
            text += source[index + 1]
            index += 2
            continue
        }
        if (character === "`") {
            const end = codeSpanEnd(source, index)
            if (end !== -1) {
                flushText()
                nodes.push({
                    type: "code",
                    text: source.slice(index + 1, end - 1),
                })
                index = end
                continue
            }
        }
        if (character === "*") {
            const marker = source[index + 1] === "*" ? "**" : "*"
            const contentStart = index + marker.length
            if (!isSpace(source[contentStart])) {
                const close = findClosing(source, contentStart, marker)
                if (close !== -1) {
                    flushText()
                    nodes.push({
                        type: marker === "**" ? "bold" : "italic",
                        children: parseRichText(
                            source.slice(contentStart, close)
                        ),
                    })
                    index = close + marker.length
                    continue
                }
            }
            text += marker
            index += marker.length
            continue
        }
        text += character
        index += 1
    }
    flushText()
    return nodes
}

function nodesToPlainText(nodes: RichTextNode[]): string {
    return nodes
        .map((node) =>
            node.type === "text" || node.type === "code"
                ? node.text
                : nodesToPlainText(node.children)
        )
        .join("")
}

/** The prompt without its markers, for alt texts, titles and window names. */
export function richTextToPlainText(source: string) {
    return nodesToPlainText(parseRichText(source))
}

export function hasRichTextFormatting(source: string) {
    return parseRichText(source).some((node) => node.type !== "text")
}

function countRun(text: string, character: string, fromEnd: boolean) {
    let count = 0
    while (
        count < text.length &&
        text[fromEnd ? text.length - 1 - count : count] === character
    )
        count += 1
    return count
}

/** Whether the text between `before` and `after` already carries `marker`. */
function isWrapped(before: string, after: string, marker: string) {
    if (marker !== "*" && marker !== "**")
        return before.endsWith(marker) && after.startsWith(marker)
    const starsBefore = countRun(before, "*", true)
    const starsAfter = countRun(after, "*", false)
    // One star is italic, two are bold, three are both.
    return marker === "*"
        ? starsBefore % 2 === 1 && starsAfter % 2 === 1
        : starsBefore >= 2 && starsAfter >= 2
}

export type RichTextSelection = {
    value: string
    selectionStart: number
    selectionEnd: number
}

/**
 * Wraps the selection in `marker`, or removes the marker when the selection
 * is already wrapped. Spaces at the edges of the selection stay outside the
 * markers, since `** word**` would not render as bold.
 */
export function toggleRichTextMarker(
    { value, selectionStart, selectionEnd }: RichTextSelection,
    marker: string
): RichTextSelection {
    let start = selectionStart
    let end = selectionEnd
    while (start < end && /\s/.test(value[start])) start += 1
    while (end > start && /\s/.test(value[end - 1])) end -= 1

    const before = value.slice(0, start)
    const selected = value.slice(start, end)
    const after = value.slice(end)

    if (isWrapped(before, after, marker)) {
        return {
            value:
                before.slice(0, -marker.length) +
                selected +
                after.slice(marker.length),
            selectionStart: start - marker.length,
            selectionEnd: end - marker.length,
        }
    }
    if (
        selected.length >= marker.length * 2 &&
        selected.startsWith(marker) &&
        selected.endsWith(marker)
    ) {
        const inner = selected.slice(marker.length, -marker.length)
        return {
            value: before + inner + after,
            selectionStart: start,
            selectionEnd: start + inner.length,
        }
    }
    return {
        value: before + marker + selected + marker + after,
        selectionStart: start + marker.length,
        selectionEnd: end + marker.length,
    }
}

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
const NOT_SCANNED = 0

function isSpace(character: string | undefined) {
    return character === undefined || /\s/.test(character)
}

/**
 * One string being parsed, with what makes scanning it cheap.
 *
 * Emphasis is matched by scanning ahead for a closing star run, and a failed
 * inner match used to be retried from every star and re-scan to the end of
 * the string: exponential time on prompts such as `"***a ".repeat(25)`. Here
 * every scan result is remembered for this string, and scans jump from one
 * significant character (`*`, `` ` ``, `\`) to the next, so each starting
 * point is scanned at most once per marker.
 */
/**
 * A cell of one of the scan tables below, which cover every index of the
 * text and the one just past its end.
 */
function cell(table: Int32Array, index: number): number {
    const value = table[index]
    if (value === undefined)
        throw new RangeError(`${index} is outside the scanned text`)
    return value
}

class RichTextSource {
    readonly text: string
    private readonly nextSignificant: Int32Array
    private readonly nextBacktick: Int32Array
    private readonly starRunEnd: Int32Array
    // The closing star run reached from each position, per marker, stored
    // plus two: the zero a new array holds means "not scanned yet", and a
    // stored one (-1 + 2) means there is none.
    private readonly boldClosings: Int32Array
    private readonly italicClosings: Int32Array

    constructor(text: string) {
        this.text = text
        const length = text.length
        this.nextSignificant = new Int32Array(length + 1)
        this.nextBacktick = new Int32Array(length + 1)
        this.starRunEnd = new Int32Array(length + 1)
        this.boldClosings = new Int32Array(length)
        this.italicClosings = new Int32Array(length)
        this.nextSignificant[length] = length
        this.nextBacktick[length] = length
        this.starRunEnd[length] = length
        for (let index = length - 1; index >= 0; index -= 1) {
            const character = text[index]
            this.starRunEnd[index] =
                character === "*" ? cell(this.starRunEnd, index + 1) : index
            this.nextBacktick[index] =
                character === "`" ? index : cell(this.nextBacktick, index + 1)
            this.nextSignificant[index] =
                character === "*" || character === "`" || character === "\\"
                    ? index
                    : cell(this.nextSignificant, index + 1)
        }
    }

    /** Index just after a closing backtick, or -1 when the span never closes. */
    codeSpanEnd(start: number) {
        const close =
            start + 1 < this.text.length
                ? cell(this.nextBacktick, start + 1)
                : -1
        return close > start + 1 && close < this.text.length ? close + 1 : -1
    }

    starRunLength(start: number) {
        return cell(this.starRunEnd, start) - start
    }

    /**
     * Index of the closing `marker` for an emphasis whose content starts at
     * `from`, or -1. Code spans and escapes are skipped, and a bold run inside
     * an italic one (or the reverse) is stepped over so it cannot close the
     * outer. In a shared run such as `***`, the inner emphasis closes on the
     * stars next to its text and the outer one on the last stars.
     */
    findClosing(from: number, marker: "*" | "**", nested = false): number {
        const source = this.text
        let start = this.skipTo(from)
        // A star run right where the content starts cannot close it.
        if (start === from && source[start] === "*")
            start = this.afterStarRun(start, marker)
        const run = this.closingRun(start, marker)
        if (run === -1) return -1
        return nested ? run : run + this.starRunLength(run) - marker.length
    }

    /**
     * The star run that closes `marker` when scanning on from `start`, or -1.
     *
     * Past its first character, a scan's path depends only on where it is,
     * not on where it began: every position on a path gets the path's
     * result, so no stretch of the string is scanned twice for a marker.
     */
    private closingRun(start: number, marker: "*" | "**"): number {
        const known = marker === "**" ? this.boldClosings : this.italicClosings
        const source = this.text
        const path: number[] = []
        let index = start
        let result = -1
        while (index < source.length) {
            const cached = cell(known, index)
            if (cached !== NOT_SCANNED) {
                result = cached - 2
                break
            }
            path.push(index)
            const character = source[index]
            if (character === "\\" && ESCAPABLE.has(source[index + 1] ?? "")) {
                index = this.skipTo(index + 2)
                continue
            }
            if (character === "`") {
                const end = this.codeSpanEnd(index)
                index = this.skipTo(end !== -1 ? end : index + 1)
                continue
            }
            if (character !== "*") {
                index = this.skipTo(index + 1)
                continue
            }
            const run = this.starRunLength(index)
            const closes = marker === "**" ? run >= 2 : run % 2 === 1
            if (!isSpace(source[index - 1]) && closes) {
                result = index
                break
            }
            index = this.afterStarRun(index, marker)
        }
        for (const visited of path) known[visited] = result + 2
        return result
    }

    /** Where a scan for `marker` goes on after the star run at `index`. */
    private afterStarRun(index: number, marker: "*" | "**"): number {
        const run = this.starRunLength(index)
        const innerMarker = run >= 2 ? "**" : "*"
        if (innerMarker !== marker && !isSpace(this.text[index + run])) {
            const innerClose = this.findClosing(
                index + innerMarker.length,
                innerMarker,
                true
            )
            if (innerClose !== -1)
                return this.skipTo(innerClose + innerMarker.length)
        }
        return this.skipTo(index + run)
    }

    skipTo(index: number) {
        return index < this.text.length
            ? cell(this.nextSignificant, index)
            : index
    }
}

export function parseRichText(source: string): RichTextNode[] {
    const parsed = new RichTextSource(source)
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
            const end = parsed.codeSpanEnd(index)
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
                const close = parsed.findClosing(contentStart, marker)
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
        // Plain characters up to the next marker, escape or backtick.
        const next = parsed.skipTo(index + 1)
        text += source.slice(index, next)
        index = next
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

/**
 * Whether the prompt uses any formatting. It runs on every keystroke in the
 * editor, so a prompt without a star or a backtick is answered without
 * parsing.
 */
export function hasRichTextFormatting(source: string) {
    if (!source.includes("*") && !source.includes("`")) return false
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
    while (start < end && /\s/.test(value[start] ?? "")) start += 1
    while (end > start && /\s/.test(value[end - 1] ?? "")) end -= 1

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

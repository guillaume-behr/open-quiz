/**
 * Trims a block of text the way the server stores it. Text on one line is
 * trimmed as usual; text on several lines loses its blank lines before and
 * its spaces after, but keeps the indentation of its first line, so a pasted
 * piece of code keeps its shape.
 */
export function trimTextBlock(value: string) {
    const text = value
        .replace(/\r\n?/g, "\n")
        .trimEnd()
        .replace(/^(?:[^\S\n]*\n)+/, "")
    return text.includes("\n") ? text : text.trim()
}

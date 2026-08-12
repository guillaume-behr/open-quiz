import { ApiError } from "@/api/client"

type ValidationIssue = {
    loc?: unknown
    msg?: unknown
}

class JsonSyntaxImportError extends Error {}

function lineAndColumn(source: string, position: number) {
    const beforeError = source.slice(0, Math.max(0, position))
    const lines = beforeError.split("\n")
    return { line: lines.length, column: (lines.at(-1)?.length ?? 0) + 1 }
}

function describeSyntaxError(error: SyntaxError, source: string): string {
    const explicitLocation = error.message.match(
        /line\s+(\d+)\s+column\s+(\d+)/i
    )
    if (explicitLocation) {
        return `JSON — line ${explicitLocation[1]}, column ${explicitLocation[2]}: ${error.message}`
    }
    const position = error.message.match(/position\s+(\d+)/i)
    if (position) {
        const location = lineAndColumn(source, Number(position[1]))
        return `JSON — line ${location.line}, column ${location.column}: ${error.message}`
    }
    const unexpectedToken = error.message.match(/Unexpected token '([^']+)'/i)
    if (unexpectedToken) {
        const tokenPosition = source.indexOf(unexpectedToken[1])
        if (tokenPosition >= 0) {
            const location = lineAndColumn(source, tokenPosition)
            return `JSON — line ${location.line}, column ${location.column}: ${error.message}`
        }
    }
    if (/unexpected end/i.test(error.message)) {
        const location = lineAndColumn(source, source.length)
        return `JSON — line ${location.line}, column ${location.column}: ${error.message}`
    }
    return `JSON: ${error.message}`
}

export async function readJsonImportFile(file: File): Promise<string> {
    const source = await file.text()
    try {
        JSON.parse(source)
    } catch (error) {
        throw new JsonSyntaxImportError(
            error instanceof SyntaxError
                ? describeSyntaxError(error, source)
                : String(error)
        )
    }
    return source
}

function validationPath(location: unknown): string {
    if (!Array.isArray(location)) return "$"
    return location
        .filter((part) => part !== "body")
        .reduce<string>(
            (path, part) =>
                typeof part === "number"
                    ? `${path}[${part}]`
                    : `${path}.${String(part)}`,
            "$"
        )
}

export function describeJsonImportFailure(
    error: unknown,
    fallback: string
): string {
    if (error instanceof JsonSyntaxImportError) return error.message
    if (error instanceof ApiError && Array.isArray(error.detail)) {
        const issue = error.detail.find(
            (item): item is ValidationIssue =>
                typeof item === "object" && item !== null
        )
        if (issue) {
            const reason =
                typeof issue.msg === "string" ? issue.msg : error.message
            return `${fallback}\n${validationPath(issue.loc)}: ${reason}`
        }
    }
    return fallback
}

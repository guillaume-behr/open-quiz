import { ApiError } from "@/api/client"

type ValidationIssue = {
    loc?: unknown
    msg?: unknown
}

type Translate = (key: string, values?: Record<string, unknown>) => string

type SyntaxLocation = { line: number; column: number }

class JsonSyntaxImportError extends Error {
    readonly reason: string
    readonly location: SyntaxLocation | null

    constructor(reason: string, location: SyntaxLocation | null) {
        super(reason)
        this.reason = reason
        this.location = location
    }
}

function lineAndColumn(source: string, position: number): SyntaxLocation {
    const beforeError = source.slice(0, Math.max(0, position))
    const lines = beforeError.split("\n")
    return { line: lines.length, column: (lines.at(-1)?.length ?? 0) + 1 }
}

function locateSyntaxError(
    error: SyntaxError,
    source: string
): SyntaxLocation | null {
    const explicitLocation = error.message.match(
        /line\s+(\d+)\s+column\s+(\d+)/i
    )
    if (explicitLocation) {
        return {
            line: Number(explicitLocation[1]),
            column: Number(explicitLocation[2]),
        }
    }
    const position = error.message.match(/position\s+(\d+)/i)
    if (position) return lineAndColumn(source, Number(position[1]))
    const unexpectedToken = error.message.match(/Unexpected token '([^']+)'/i)
    if (unexpectedToken) {
        const tokenPosition = source.indexOf(unexpectedToken[1])
        if (tokenPosition >= 0) return lineAndColumn(source, tokenPosition)
    }
    if (/unexpected end/i.test(error.message)) {
        return lineAndColumn(source, source.length)
    }
    return null
}

export async function readJsonImportFile(file: File): Promise<string> {
    const source = await file.text()
    try {
        JSON.parse(source)
    } catch (error) {
        throw new JsonSyntaxImportError(
            error instanceof Error ? error.message : String(error),
            error instanceof SyntaxError
                ? locateSyntaxError(error, source)
                : null
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

/**
 * What to tell the teacher about a failed import: where the file is not valid
 * JSON, or which field the server refused (with the server's own reason).
 */
export function describeJsonImportFailure(
    error: unknown,
    t: Translate,
    fallback: string
): string {
    if (error instanceof JsonSyntaxImportError) {
        return error.location
            ? t("json-syntax-error-at", {
                  ...error.location,
                  message: error.reason,
              })
            : t("json-syntax-error", { message: error.reason })
    }
    if (error instanceof ApiError && Array.isArray(error.detail)) {
        const issue = error.detail.find(
            (item): item is ValidationIssue =>
                typeof item === "object" && item !== null
        )
        if (issue) {
            const reason =
                typeof issue.msg === "string" ? issue.msg : error.message
            return `${fallback}\n${t("json-invalid-field", {
                path: validationPath(issue.loc),
                reason,
            })}`
        }
    }
    return fallback
}

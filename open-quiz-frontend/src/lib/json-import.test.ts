import { describe, expect, it } from "vitest"

import { ApiError } from "@/api/client"
import {
    describeJsonImportFailure,
    readJsonImportFile,
} from "@/lib/json-import"

// A stand-in for i18next's t: the key and its values, to check both.
function t(key: string, values?: Record<string, unknown>): string {
    return values ? `${key} ${JSON.stringify(values)}` : key
}

function jsonFile(source: string): File {
    return new File([source], "bank.json", { type: "application/json" })
}

async function syntaxFailure(source: string): Promise<string> {
    try {
        await readJsonImportFile(jsonFile(source))
    } catch (error) {
        return describeJsonImportFailure(error, t, "fallback")
    }
    throw new Error("the file was accepted")
}

describe("readJsonImportFile", () => {
    it("returns the source of a valid file unchanged", async () => {
        const source = '{\n  "version": 1\n}'
        await expect(readJsonImportFile(jsonFile(source))).resolves.toBe(source)
    })

    it("locates a syntax error by line and column", async () => {
        const message = await syntaxFailure('{\n  "version": 1,\n  oops\n}')
        expect(message).toMatch(
            /^json-syntax-error-at \{"line":3,"column":3,"message":".+"\}$/
        )
    })

    it("locates a truncated file at its end", async () => {
        const message = await syntaxFailure('{\n  "version": 1,')
        expect(message).toMatch(
            /^json-syntax-error-at \{"line":2,"column":16,"message":".+"\}$/
        )
    })
})

describe("describeJsonImportFailure", () => {
    it("names the field of an API validation error", () => {
        const error = new ApiError("Unprocessable", 422, [
            {
                loc: ["body", "questions", 2, "prompt"],
                msg: "Field required",
            },
        ])
        expect(describeJsonImportFailure(error, t, "Import failed")).toBe(
            'Import failed\njson-invalid-field {"path":"$.questions[2].prompt","reason":"Field required"}'
        )
    })

    it("falls back for any other failure", () => {
        expect(
            describeJsonImportFailure(new Error("network"), t, "Failed")
        ).toBe("Failed")
        expect(
            describeJsonImportFailure(
                new ApiError("Conflict", 409, { code: "X" }),
                t,
                "Failed"
            )
        ).toBe("Failed")
    })
})

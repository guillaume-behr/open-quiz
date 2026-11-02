import { describe, expect, it } from "vitest"

import { ApiError } from "@/api/client"
import {
    describeJsonImportFailure,
    readJsonImportFile,
} from "@/lib/json-import"

function jsonFile(source: string): File {
    return new File([source], "bank.json", { type: "application/json" })
}

async function syntaxFailure(source: string): Promise<string> {
    try {
        await readJsonImportFile(jsonFile(source))
    } catch (error) {
        return describeJsonImportFailure(error, "fallback")
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
        expect(message).toMatch(/^JSON — line 3, column 3: /)
    })

    it("locates a truncated file at its end", async () => {
        const message = await syntaxFailure('{\n  "version": 1,')
        expect(message).toMatch(/^JSON — line 2, column 16: /)
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
        expect(describeJsonImportFailure(error, "Import failed")).toBe(
            "Import failed\n$.questions[2].prompt: Field required"
        )
    })

    it("falls back for any other failure", () => {
        expect(describeJsonImportFailure(new Error("network"), "Failed")).toBe(
            "Failed"
        )
        expect(
            describeJsonImportFailure(
                new ApiError("Conflict", 409, { code: "X" }),
                "Failed"
            )
        ).toBe("Failed")
    })
})

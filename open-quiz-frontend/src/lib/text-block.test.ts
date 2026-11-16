import { describe, expect, it } from "vitest"

import { trimTextBlock } from "./text-block"

describe("trimTextBlock", () => {
    it("keeps the indentation of the first line and the line breaks", () => {
        expect(trimTextBlock("    if x:\n        return 1\n")).toBe(
            "    if x:\n        return 1"
        )
    })

    it("drops the blank lines around the text", () => {
        expect(trimTextBlock("\n  \n\tf(\n\t  x)\n\n  ")).toBe("\tf(\n\t  x)")
    })

    it("normalises Windows and old Mac line breaks", () => {
        expect(trimTextBlock("a\r\n  b\rc")).toBe("a\n  b\nc")
    })

    it("returns an empty string for blank text", () => {
        expect(trimTextBlock(" \n\t\n ")).toBe("")
    })
})

describe("trimTextBlock on one line", () => {
    it("trims both ends", () => {
        expect(trimTextBlock("  Label  ")).toBe("Label")
        expect(trimTextBlock("\n   x = 1\n")).toBe("x = 1")
    })
})

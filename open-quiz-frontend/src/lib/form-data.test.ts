import { describe, expect, it } from "vitest"
import { formText } from "./form-data"

describe("formText", () => {
    it("returns a text field, and an empty string otherwise", () => {
        const form = new FormData()
        form.set("name", "Ada")
        form.set("upload", new File(["x"], "x.txt"))
        expect(formText(form, "name")).toBe("Ada")
        expect(formText(form, "upload")).toBe("")
        expect(formText(form, "missing")).toBe("")
    })
})

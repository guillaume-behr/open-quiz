// @vitest-environment jsdom
import { describe, expect, it } from "vitest"

import type { StudentClass, StudentCredential } from "@/api/types"

import { writeCredentialCards } from "./print-credentials"

const t = ((key: string, options?: { className?: string }) =>
    options?.className ? `${key} ${options.className}` : key) as never
const studentClass = { grade_level: "Tle", name: "1" } as StudentClass

describe("writeCredentialCards", () => {
    it("writes one card per student, names and passwords as text", () => {
        const doc = document.implementation.createHTMLDocument("")
        const credentials = [
            {
                display_name: `<img src=x onerror=alert(1)> "O'Neil" & co`,
                identifier: "o.neil",
                password: "<b>pw</b>",
            },
            { display_name: "Ada", identifier: "ada", password: null },
        ] as StudentCredential[]
        writeCredentialCards(doc, studentClass, credentials, t, "ar", "rtl")
        expect(doc.documentElement.dir).toBe("rtl")
        expect(doc.documentElement.lang).toBe("ar")
        expect(doc.title).toContain("student-credentials-print-title")
        expect(doc.querySelectorAll("article")).toHaveLength(2)
        expect(doc.querySelector("main img, main b")).toBeNull()
        expect(doc.querySelector(".name")?.textContent).toBe(
            `<img src=x onerror=alert(1)> "O'Neil" & co`
        )
        expect(doc.body.textContent).toContain("<b>pw</b>")
        expect(doc.body.textContent).toContain("password-unavailable")
    })

    it("says so when the class has no student", () => {
        const doc = document.implementation.createHTMLDocument("")
        writeCredentialCards(doc, studentClass, [], t, "en", "ltr")
        expect(doc.querySelector(".empty")?.textContent).toBe(
            "no-student-in-class"
        )
    })
})

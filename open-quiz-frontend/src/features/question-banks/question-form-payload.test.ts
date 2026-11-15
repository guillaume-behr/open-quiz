import { describe, expect, it } from "vitest"

import { choicePayloads } from "./question-form-payload"
import type { EditableChoice } from "./question-form-types"

function choice(overrides: Partial<EditableChoice> = {}): EditableChoice {
    return {
        uid: 1,
        label: " Label ",
        is_correct: false,
        points: 0,
        has_image: false,
        remove_image: false,
        hasCode: false,
        codeLanguage: "javascript",
        codeContent: "",
        ...overrides,
    }
}

function png(name: string): File {
    return new File(["image"], name, { type: "image/png" })
}

describe("choicePayloads", () => {
    it("sends new images as files that the choices name by position", () => {
        const first = png("first.png")
        const third = png("third.png")
        const { payloads, images } = choicePayloads([
            choice({ id: 4, image: first, is_correct: true, points: 1 }),
            choice({ has_image: true }),
            choice({ image: third, hasCode: true, codeContent: "x = 1" }),
        ])

        expect(images).toEqual([first, third])
        expect(payloads.map((payload) => payload.image_file)).toEqual([
            0,
            null,
            1,
        ])
        expect(payloads[0]).toMatchObject({
            id: 4,
            label: "Label",
            is_correct: true,
            points: 1,
            remove_image: false,
            code_language: null,
            code_content: null,
        })
        expect(payloads[2]).toMatchObject({
            code_language: "javascript",
            code_content: "x = 1",
        })
        expect(JSON.stringify(payloads)).not.toContain("base64")
    })

    it("refuses an image type the server does not accept", () => {
        const svg = new File(["<svg/>"], "a.svg", { type: "image/svg+xml" })
        expect(() => choicePayloads([choice({ image: svg })])).toThrow(
            "Unsupported image type"
        )
    })
})

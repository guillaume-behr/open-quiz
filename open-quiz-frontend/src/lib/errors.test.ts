import { describe, expect, it } from "vitest"

import { ApiError } from "@/api/client"
import { API_ERROR_TRANSLATION_KEYS, apiErrorMessage } from "@/lib/errors"

const translate = (key: string) => `translated:${key}`

describe("apiErrorMessage", () => {
    it("translates a known API code", () => {
        const error = new ApiError("Quiz introuvable", 404, {
            code: "QUIZ_NOT_FOUND",
            message: "Quiz introuvable",
        })
        expect(apiErrorMessage(error, translate, "fallback")).toBe(
            `translated:${API_ERROR_TRANSLATION_KEYS.QUIZ_NOT_FOUND}`
        )
    })

    it("keeps the screen's fallback for anything else", () => {
        const unknownCode = new ApiError("?", 409, { code: "NOT_A_CODE" })
        const withoutCode = new ApiError("Erreur", 500, "Erreur")
        const network = new TypeError("Failed to fetch")
        for (const error of [unknownCode, withoutCode, network, "boom"]) {
            expect(apiErrorMessage(error, translate, "fallback")).toBe(
                "fallback"
            )
        }
    })
})

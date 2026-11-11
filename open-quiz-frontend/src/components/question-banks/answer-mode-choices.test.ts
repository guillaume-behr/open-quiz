import { describe, expect, it } from "vitest"
import { fitChoicesToMode, nextChoiceUid } from "./answer-mode-choices"
import type { EditableChoice } from "./question-form-types"

function choice(label: string, isCorrect: boolean): EditableChoice {
    return {
        uid: nextChoiceUid(),
        label,
        is_correct: isCorrect,
        points: 0,
        has_image: false,
        remove_image: false,
        hasCode: false,
        codeLanguage: "javascript",
        codeContent: "",
    }
}

const correctLabels = (choices: EditableChoice[]) =>
    choices.filter((item) => item.is_correct).map((item) => item.label)

describe("fitChoicesToMode", () => {
    it("restores a single-choice answer key exactly", () => {
        const choices = [
            choice("a", false),
            choice("b", false),
            choice("c", true),
        ]
        const fitted = fitChoicesToMode(choices, "single")
        expect(fitted.choices).toBe(choices)
        expect(fitted.keptFirstCorrectOnly).toBe(false)
    })

    it("keeps only the first correct choice when single choice gets several", () => {
        const choices = [
            choice("a", false),
            choice("b", true),
            choice("c", true),
        ]
        const fitted = fitChoicesToMode(choices, "single")
        expect(correctLabels(fitted.choices)).toEqual(["b"])
        expect(fitted.keptFirstCorrectOnly).toBe(true)
        expect(correctLabels(choices)).toEqual(["b", "c"])
    })

    it("preselects nothing when no choice is correct", () => {
        const choices = [choice("a", false), choice("b", false)]
        expect(
            correctLabels(fitChoicesToMode(choices, "single").choices)
        ).toEqual([])
    })

    it("keeps every correct choice for multiple choice", () => {
        const choices = [choice("a", true), choice("b", true)]
        const fitted = fitChoicesToMode(choices, "multiple")
        expect(fitted.choices).toBe(choices)
        expect(fitted.keptFirstCorrectOnly).toBe(false)
    })
})

describe("nextChoiceUid", () => {
    it("never repeats", () => {
        const uids = Array.from({ length: 5 }, nextChoiceUid)
        expect(new Set(uids).size).toBe(5)
    })
})

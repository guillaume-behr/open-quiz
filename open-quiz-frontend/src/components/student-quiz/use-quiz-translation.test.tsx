// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react"
import type { i18n } from "i18next"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { StudentQuizSession } from "@/api/types"

import { useQuizTranslation } from "./use-quiz-translation"

const translatorApi = vi.hoisted(() => ({
    createBrowserTranslator: vi.fn(),
    translationLanguage: (value: string | null | undefined) => value ?? "fr",
}))
vi.mock("@/lib/browser-translator", () => translatorApi)
const content = vi.hoisted(() => ({
    translateQuestion: vi.fn(),
    translateAnswerSummary: vi.fn(),
}))
vi.mock("./student-quiz-translation", () => content)

function fakeTranslator() {
    return {
        translate: vi.fn((value: string) => Promise.resolve(`[${value}]`)),
        destroy: vi.fn(),
    }
}

function session(questionId: number | null, summaries: string[] = []) {
    return {
        quiz_title: "Titre",
        source_language: "fr",
        question:
            questionId === null
                ? null
                : { id: questionId, prompt: `Q${questionId}` },
        answer_summaries: summaries.map((answer, index) => ({
            question_id: index,
            submitted_answers: [answer],
        })),
    } as unknown as StudentQuizSession
}

function render(initial: StudentQuizSession | null, language = "en") {
    return renderHook(
        ({ value, lang }) =>
            useQuizTranslation(value, { resolvedLanguage: lang } as i18n),
        { initialProps: { value: initial, lang: language } }
    )
}

describe("useQuizTranslation", () => {
    let translator: ReturnType<typeof fakeTranslator>

    beforeEach(() => {
        translator = fakeTranslator()
        translatorApi.createBrowserTranslator.mockImplementation(
            (_source: string, _target: string, onDownload: () => void) => {
                onDownload()
                return Promise.resolve(translator)
            }
        )
        content.translateQuestion.mockImplementation(
            (_: unknown, question: { id: number; prompt: string }) =>
                Promise.resolve({ ...question, prompt: `[${question.prompt}]` })
        )
        content.translateAnswerSummary.mockImplementation(
            (_: unknown, summary: object) =>
                Promise.resolve({ ...summary, translated: true })
        )
    })

    it("is not offered without a session or in the quiz's own language", async () => {
        const { result, rerender } = render(null)
        expect(result.current.viewState.offered).toBe(false)
        await act(() => result.current.toggle())
        expect(translatorApi.createBrowserTranslator).not.toHaveBeenCalled()
        rerender({ value: session(1), lang: "fr" })
        expect(result.current.viewState.offered).toBe(false)
        expect(result.current.title).toBe("Titre")
    })

    it("translates the title, questions and answer review, then turns off", async () => {
        const { result, rerender } = render(session(1))
        expect(result.current.viewState.offered).toBe(true)
        await act(() => result.current.toggle())
        expect(result.current.viewState.active).toBe(true)
        expect(result.current.title).toBe("[Titre]")
        expect(result.current.question?.prompt).toBe("[Q1]")
        await expect(result.current.translateText("note")).resolves.toBe(
            "[note]"
        )
        await expect(result.current.translateText("")).resolves.toBeNull()

        rerender({ value: session(2, ["a", "b"]), lang: "en" })
        await waitFor(() =>
            expect(result.current.question?.prompt).toBe("[Q2]")
        )
        await waitFor(() =>
            expect(result.current.answerSummaries[0]).toMatchObject({
                translated: true,
            })
        )

        await act(() => result.current.toggle())
        expect(result.current.viewState.active).toBe(false)
        expect(result.current.question?.prompt).toBe("Q2")
        await expect(result.current.translateText("note")).resolves.toBeNull()

        // Turning it on again reuses the downloaded model.
        await act(() => result.current.toggle())
        expect(translatorApi.createBrowserTranslator).toHaveBeenCalledTimes(1)
        expect(result.current.viewState.active).toBe(true)
    })

    it("shows an error when the model or a translation fails", async () => {
        translatorApi.createBrowserTranslator.mockRejectedValueOnce(
            new Error("unsupported")
        )
        const { result, rerender } = render(session(1))
        await act(() => result.current.toggle())
        expect(result.current.viewState.hasError).toBe(true)
        expect(result.current.viewState.isTranslating).toBe(false)

        await act(() => result.current.toggle())
        expect(result.current.viewState.active).toBe(true)
        content.translateQuestion.mockRejectedValue(new Error("busy"))
        content.translateAnswerSummary.mockRejectedValue(new Error("busy"))
        translator.translate.mockRejectedValue(new Error("busy"))
        rerender({ value: session(3, ["a"]), lang: "en" })
        await waitFor(() =>
            expect(result.current.viewState.hasError).toBe(true)
        )
        expect(result.current.question?.prompt).toBe("Q3")
        await expect(result.current.translateText("note")).resolves.toBeNull()
    })

    it("drops a model that arrives after a reset", async () => {
        let deliver: (value: unknown) => void = () => undefined
        translatorApi.createBrowserTranslator.mockImplementation(
            () => new Promise((resolve) => (deliver = resolve))
        )
        const { result } = render(session(null))
        let toggling: Promise<void> = Promise.resolve()
        act(() => {
            toggling = result.current.toggle()
        })
        expect(result.current.viewState.isTranslating).toBe(true)
        act(() => result.current.reset())
        await act(async () => {
            deliver(translator)
            await toggling
        })
        expect(translator.destroy).toHaveBeenCalled()
        expect(result.current.viewState.active).toBe(false)
    })

    it("starts over when the student's language changes", async () => {
        const { result, rerender, unmount } = render(session(1))
        await act(() => result.current.toggle())
        expect(result.current.viewState.active).toBe(true)
        rerender({ value: session(1), lang: "de" })
        expect(translator.destroy).toHaveBeenCalled()
        expect(result.current.viewState.active).toBe(false)
        await waitFor(() => expect(result.current.title).toBe("Titre"))

        const german = fakeTranslator()
        translatorApi.createBrowserTranslator.mockResolvedValue(german)
        await act(() => result.current.toggle())
        expect(result.current.title).toBe("[Titre]")
        unmount()
        expect(german.destroy).toHaveBeenCalled()
    })
})

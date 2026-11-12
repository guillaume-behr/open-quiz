// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { Quiz, StudentClass } from "@/api/types"

import { printExamSubjects } from "./print-quiz"

const api = vi.hoisted(() => ({
    getQuestions: vi.fn(),
    getQuestionImage: vi.fn(),
    getChoiceImage: vi.fn(),
}))
vi.mock("@/api/question-banks", () => api)

const hostile = `<script>alert("x")</script> & "quotes"`
const questions = [
    {
        id: 1,
        difficulty: "easy",
        answer_mode: "single",
        prompt: `**Bold** *it* \`code\` ${hostile}`,
        has_image: true,
        code_content: "print(1)",
        code_language: "python",
        choices: [
            {
                id: 11,
                label: hostile,
                has_image: true,
                code_content: "x = 1",
                code_language: "unknown-language",
            },
            { id: 12, label: "B", has_image: false, code_content: null },
        ],
    },
    {
        id: 2,
        difficulty: "easy",
        answer_mode: "written",
        prompt: "Explain",
        has_image: false,
        code_content: null,
        code_language: null,
        choices: [],
    },
]
const quiz = {
    id: 5,
    title: "Exam & co",
    question_banks: [{ id: 9 }],
    easy_question_count: 2,
    medium_question_count: 0,
    hard_question_count: 0,
} as unknown as Quiz
const studentClass = {
    id: 3,
    grade_level: "Tle",
    name: "1",
    students: [{}, {}],
} as unknown as StudentClass
const t = ((key: string, options?: { label?: string }) =>
    options?.label ? `${options.label}:` : key) as never

function fakeWindow() {
    const document = window.document.implementation.createHTMLDocument("")
    const timers: (() => void)[] = []
    const listeners: (() => void)[] = []
    return {
        window: {
            document,
            opener: {},
            focus: vi.fn(),
            print: vi.fn(),
            setTimeout: (callback: () => void) => timers.push(callback),
            addEventListener: (_: string, listener: () => void) =>
                listeners.push(listener),
        } as unknown as Window,
        timers,
        listeners,
    }
}

describe("printExamSubjects", () => {
    beforeEach(() => {
        api.getQuestions.mockResolvedValue(questions)
        api.getQuestionImage.mockResolvedValue(new Blob(["q"]))
        api.getChoiceImage.mockResolvedValue(new Blob(["c"]))
        let next = 0
        vi.stubGlobal("URL", {
            createObjectURL: vi.fn(() => `blob:${++next}`),
            revokeObjectURL: vi.fn(),
        })
    })

    it("writes one copy per student with every text as text", async () => {
        const { window: printWindow, timers, listeners } = fakeWindow()
        const printing = printExamSubjects(
            quiz,
            studentClass,
            printWindow,
            t,
            "fr"
        )
        const doc = printWindow.document
        // The print dialog waits for every image to load or fail.
        await vi.waitFor(() => expect(doc.images.length).toBeGreaterThan(0))
        expect(printWindow.print).not.toHaveBeenCalled()
        Array.from(doc.images).forEach((image, index) =>
            image.dispatchEvent(new Event(index === 0 ? "error" : "load"))
        )
        await printing
        expect(printWindow.opener).toBeNull()
        expect(doc.title).toBe("Exam & co")
        expect(doc.documentElement.lang).toBe("fr")
        expect(doc.querySelectorAll("section.subject")).toHaveLength(2)
        expect(doc.querySelector("script")).toBeNull()
        const text = doc.body.textContent ?? ""
        expect(text).toContain(hostile)
        expect(doc.querySelector("h2 strong")?.textContent).toBe("Bold")
        expect(doc.querySelector("h2 em")?.textContent).toBe("it")
        expect(doc.querySelector("h2 code")?.textContent).toBe("code")
        expect(doc.querySelectorAll(".writing")).toHaveLength(2)
        expect(doc.querySelectorAll(".question-image")).toHaveLength(2)
        expect(doc.querySelectorAll(".choice-image")).toHaveLength(2)
        expect(
            [...doc.querySelectorAll(".code-language")].map(
                (n) => n.textContent
            )
        ).toContain("unknown-language")
        // Each image is fetched once even if several copies show it.
        expect(api.getQuestionImage).toHaveBeenCalledTimes(1)

        for (const timer of timers) timer()
        expect(printWindow.print).toHaveBeenCalled()
        expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
        for (const listener of listeners) listener()
        expect(URL.revokeObjectURL).toHaveBeenCalledTimes(2)
    })

    it("prints the same copies twice", async () => {
        vi.spyOn(HTMLImageElement.prototype, "complete", "get").mockReturnValue(
            true
        )
        const first = fakeWindow().window
        const second = fakeWindow().window
        await printExamSubjects(quiz, studentClass, first, t, "fr")
        await printExamSubjects(quiz, studentClass, second, t, "fr")
        const markup = (target: Window) =>
            target.document.body.innerHTML.replace(/blob:\d+/g, "blob")
        expect(markup(first)).toBe(markup(second))
    })

    it("releases loaded images when another fails", async () => {
        api.getChoiceImage.mockRejectedValue(new Error("missing"))
        const { window: printWindow } = fakeWindow()
        await expect(
            printExamSubjects(quiz, studentClass, printWindow, t, "fr")
        ).rejects.toThrow("missing")
        expect(URL.revokeObjectURL).toHaveBeenCalledTimes(
            vi.mocked(URL.createObjectURL).mock.calls.length
        )
        expect(printWindow.document.body.childElementCount).toBe(0)
    })
})

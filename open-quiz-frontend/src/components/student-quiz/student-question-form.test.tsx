// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import type { StudentQuizQuestion, StudentQuizSession } from "@/api/types"

import { StudentQuestionForm } from "./student-question-form"

// The code editor and protected images load browser-only machinery.
vi.mock("@/components/question-banks/code-block", () => ({
    CodeBlock: (props: {
        code: string
        editable?: boolean
        onCodeChange?: (code: string) => void
    }) =>
        props.editable ? (
            <textarea
                aria-label="code editor"
                value={props.code}
                onChange={(event) => props.onCodeChange?.(event.target.value)}
            />
        ) : (
            <pre>{props.code}</pre>
        ),
    StaticCodeBlock: (props: { code: string }) => <pre>{props.code}</pre>,
}))
vi.mock("./protected-quiz-image", () => ({
    ProtectedQuizImage: (props: { alt: string }) => <img alt={props.alt} />,
}))

const session = {
    join_code: "ABC123",
    question_number: 2,
    total_questions: 4,
    allow_previous_questions: true,
    accessible_question_numbers: [1, 2],
} as unknown as StudentQuizSession

function question(
    overrides: Partial<StudentQuizQuestion>
): StudentQuizQuestion {
    return {
        id: 7,
        prompt: "**Pick** one",
        answer_mode: "single",
        answer_mode_disclosed: true,
        has_image: false,
        code_content: null,
        code_language: null,
        response_language: null,
        allow_code_execution: false,
        total_points: 2,
        choices: [
            {
                id: "a",
                label: "Yes",
                has_image: true,
                code_content: null,
                code_language: null,
            },
            {
                id: "b",
                label: "No",
                has_image: false,
                code_content: "x = 1",
                code_language: "python",
            },
        ],
        ...overrides,
    } as StudentQuizQuestion
}

function form(
    value: StudentQuizQuestion,
    state: {
        selected?: string[]
        written?: string
        busy?: boolean
        error?: string
    } = {}
) {
    const handlers = {
        onSelectedChoiceIdsChange: vi.fn(),
        onWrittenAnswerChange: vi.fn(),
        onNavigate: vi.fn(),
        onSubmit: vi.fn((event: { preventDefault: () => void }) =>
            event.preventDefault()
        ),
    }
    render(
        <StudentQuestionForm
            session={session}
            question={value}
            participantToken="token"
            contentDirection="ltr"
            selectedChoiceIds={state.selected ?? []}
            writtenAnswer={state.written ?? ""}
            isBusy={state.busy ?? false}
            error={state.error ?? null}
            {...handlers}
        />
    )
    return handlers
}

const submitButton = () =>
    screen.getByRole("button", { name: "student-submit-answer" })

describe("StudentQuestionForm", () => {
    it("selects one choice in single mode and submits once one is chosen", async () => {
        const handlers = form(question({}))
        expect(screen.getByRole("progressbar")).toHaveAttribute(
            "aria-valuenow",
            "2"
        )
        expect(screen.getByText("single-choice")).toBeInTheDocument()
        expect(screen.getByRole("img", { name: "Yes" })).toBeInTheDocument()
        expect(screen.getByText("x = 1")).toBeInTheDocument()
        expect(submitButton()).toBeDisabled()
        await userEvent.click(screen.getByRole("radio", { name: /^No/ }))
        expect(handlers.onSelectedChoiceIdsChange).toHaveBeenCalledWith(["b"])
    })

    it("toggles choices in multiple mode", async () => {
        const handlers = form(question({ answer_mode: "multiple" }), {
            selected: ["a"],
        })
        await userEvent.click(screen.getByRole("checkbox", { name: /^Yes/ }))
        expect(handlers.onSelectedChoiceIdsChange).toHaveBeenLastCalledWith([])
        await userEvent.click(screen.getByRole("checkbox", { name: /^No/ }))
        expect(handlers.onSelectedChoiceIdsChange).toHaveBeenLastCalledWith([
            "a",
            "b",
        ])
        await userEvent.click(submitButton())
        expect(handlers.onSubmit).toHaveBeenCalled()
    })

    it("hides whether one or several answers are expected when undisclosed", () => {
        form(question({ answer_mode_disclosed: false }))
        expect(
            screen.getByText("answer-mode-not-disclosed")
        ).toBeInTheDocument()
        expect(screen.getAllByRole("checkbox")).toHaveLength(2)
    })

    it("takes a written answer and refuses a blank one", () => {
        const written = question({
            answer_mode: "written",
            choices: [],
            has_image: true,
            code_content: "print(1)",
            code_language: "python",
        })
        const handlers = form(written, { written: "   " })
        expect(screen.getByText("plain-text-response")).toBeInTheDocument()
        expect(screen.getByRole("img")).toBeInTheDocument()
        expect(submitButton()).toBeDisabled()
        fireEvent.change(
            screen.getByRole("textbox", { name: "written-answer" }),
            {
                target: { value: "Because" },
            }
        )
        expect(handlers.onWrittenAnswerChange).toHaveBeenCalledWith("Because")
    })

    it("takes code in the expected language", () => {
        const handlers = form(
            question({
                answer_mode: "written",
                choices: [],
                response_language: "python",
            }),
            { written: "print(2)" }
        )
        expect(
            screen.getByText('write-code-in-language {"language":"Python"}')
        ).toBeInTheDocument()
        fireEvent.change(screen.getByRole("textbox", { name: "code editor" }), {
            target: { value: "print(3)" },
        })
        expect(handlers.onWrittenAnswerChange).toHaveBeenCalledWith("print(3)")
        expect(submitButton()).toBeEnabled()
    })

    it("navigates to an earlier question and shows errors and progress", async () => {
        const handlers = form(question({}), {
            selected: ["a"],
            error: "Too late",
        })
        expect(screen.getByText("Too late")).toBeInTheDocument()
        const previous = screen.getByRole("button", {
            name: 'student-question-progress {"current":1,"total":4}',
        })
        await userEvent.click(previous)
        expect(handlers.onNavigate).toHaveBeenCalledWith(1)
        expect(
            screen.getByRole("button", {
                name: 'student-question-progress {"current":2,"total":4}',
            })
        ).toBeDisabled()
    })
})

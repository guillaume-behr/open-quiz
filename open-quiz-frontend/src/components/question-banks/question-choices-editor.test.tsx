// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import type { AnswerMode } from "@/api/types"

import { QuestionChoicesEditor } from "./question-choices-editor"
import type { EditableChoice } from "./question-form-types"

function choice(uid: number, label: string, isCorrect = false): EditableChoice {
    return {
        uid,
        label,
        is_correct: isCorrect,
        points: isCorrect ? 1 : 0,
        has_image: false,
        remove_image: false,
        hasCode: false,
        codeLanguage: "javascript",
        codeContent: "",
    }
}

function editor(answerMode: AnswerMode, choices: EditableChoice[]) {
    const handlers = {
        onChoicesChange: vi.fn(),
        onCorrectChoiceChange: vi.fn(),
        onRemoveChoice: vi.fn(),
    }
    render(
        <QuestionChoicesEditor
            choices={choices}
            answerMode={answerMode}
            responseLanguage={null}
            {...handlers}
        />
    )
    return handlers
}

describe("QuestionChoicesEditor", () => {
    it("adds, edits, marks correct and removes choices", async () => {
        const choices = [
            choice(1, "Yes", true),
            choice(2, "No"),
            choice(3, "Maybe"),
        ]
        const handlers = editor("single", choices)
        await userEvent.click(
            screen.getByRole("button", { name: "add-choice" })
        )
        const added = handlers.onChoicesChange.mock
            .lastCall?.[0] as EditableChoice[]
        expect(added).toHaveLength(4)
        expect(added[3]).toMatchObject({
            label: "",
            is_correct: false,
            points: 0,
        })

        fireEvent.change(screen.getByDisplayValue("No"), {
            target: { value: "Non" },
        })
        expect(
            (handlers.onChoicesChange.mock.lastCall?.[0] as EditableChoice[])[1]
        ).toMatchObject({ uid: 2, label: "Non" })

        await userEvent.click(
            screen.getByRole("radio", {
                name: 'correct-answer-number {"number":2}',
            })
        )
        expect(handlers.onCorrectChoiceChange).toHaveBeenCalledWith(1, true)

        await userEvent.click(
            screen.getByRole("button", {
                name: 'remove-choice-number {"number":3}',
            })
        )
        expect(handlers.onRemoveChoice).toHaveBeenCalledWith(2)
    })

    it("keeps two choices at least and twelve at most", () => {
        editor("multiple", [choice(1, "A"), choice(2, "B")])
        expect(
            screen.getByRole("checkbox", {
                name: 'correct-answer-number {"number":1}',
            })
        ).toBeInTheDocument()
        expect(
            screen.getByRole("button", {
                name: 'remove-choice-number {"number":1}',
            })
        ).toBeDisabled()
    })

    it("disables adding past twelve choices", () => {
        editor(
            "single",
            Array.from({ length: 12 }, (_, index) => choice(index, `C${index}`))
        )
        expect(
            screen.getByRole("button", { name: "add-choice" })
        ).toBeDisabled()
    })

    it("shows a single expected answer for a written question", () => {
        const handlers = editor("written", [
            choice(1, "42"),
            choice(2, "ignored"),
        ])
        expect(screen.getByText("expected-written-answer")).toBeInTheDocument()
        expect(screen.queryByDisplayValue("ignored")).toBeNull()
        expect(screen.queryByRole("button", { name: "add-choice" })).toBeNull()
        fireEvent.change(screen.getByDisplayValue("42"), {
            target: { value: "43" },
        })
        expect(
            (handlers.onChoicesChange.mock.lastCall?.[0] as EditableChoice[])[0]
        ).toMatchObject({ label: "43" })
    })
})

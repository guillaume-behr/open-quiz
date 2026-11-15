// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import type { StudentQuizSession } from "@/api/types"

import { AnswerReview } from "./answer-review"

const summary = (questionNumber: number, submittedAnswers: string[]) => ({
    question_number: questionNumber,
    question_id: questionNumber,
    prompt: `Question ${questionNumber}`,
    answer_mode: "written",
    submitted_answers: submittedAnswers,
})

const session = {
    allow_previous_questions: true,
    total_questions: 3,
    skipped_question_numbers: [2, 3],
    answer_summaries: [
        summary(1, ["one"]),
        // Skipped, then answered: still orange.
        summary(2, ["two"]),
        // Skipped and left unanswered.
        summary(3, []),
    ],
} as unknown as StudentQuizSession

describe("AnswerReview", () => {
    it("shows the skipped questions in orange, answered since or not", () => {
        render(
            <AnswerReview
                session={session}
                contentDirection="ltr"
                isBusy={false}
                error={null}
                onNavigate={() => undefined}
                onSubmitQuiz={() => undefined}
            />
        )
        const items = screen.getAllByRole("listitem")

        expect(items[0]).not.toHaveClass("bg-orange-50")
        expect(items[1]).toHaveClass("bg-orange-50")
        expect(items[2]).toHaveClass("bg-orange-50")
        expect(
            screen.getAllByText("student-question-state-skipped")
        ).toHaveLength(2)
    })
})

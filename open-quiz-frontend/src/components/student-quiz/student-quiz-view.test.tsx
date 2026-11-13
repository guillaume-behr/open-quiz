// @vitest-environment jsdom
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"

import type { StudentQuizQuestion, StudentQuizSession } from "@/api/types"

import { StudentQuizView } from "./student-quiz-view"

const timerRenders = vi.hoisted(() => ({ count: 0 }))
vi.mock("@/components/quizzes/quiz-timer", () => ({
    QuizTimer: () => {
        timerRenders.count += 1
        return <p>timer</p>
    },
}))
vi.mock("./student-question-form", () => ({
    StudentQuestionForm: (props: {
        writtenAnswer: string
        onSkip?: () => void
    }) => (
        <>
            <p>answer: {props.writtenAnswer}</p>
            {props.onSkip && <p>skip offered</p>}
        </>
    ),
}))

const session = {
    status: "in_progress",
    awaiting_final_submission: false,
    allow_answer_review: false,
    total_questions: 3,
    answered_count: 0,
    student_name: "Ada",
    class_name: "1A",
    ends_at: "2026-01-01T10:00:00Z",
    server_now: "2026-01-01T09:00:00Z",
} as unknown as StudentQuizSession

const question = { id: 1 } as unknown as StudentQuizQuestion

function page(
    writtenAnswer: string,
    overrides: Partial<StudentQuizSession> = {}
) {
    return (
        <StudentQuizView
            // The same object when unchanged, as the memoised header expects.
            session={
                Object.keys(overrides).length > 0
                    ? { ...session, ...overrides }
                    : session
            }
            question={question}
            participantToken="token"
            title="Quiz"
            liveReconnecting={false}
            contentDirection="ltr"
            selectedChoiceIds={[]}
            writtenAnswer={writtenAnswer}
            isBusy={false}
            error={null}
            translation={{
                offered: false,
                active: false,
                hasError: false,
                isTranslating: false,
                isDownloading: false,
            }}
            onToggleTranslation={() => undefined}
            onSelectedChoiceIdsChange={() => undefined}
            onWrittenAnswerChange={() => undefined}
            onNavigate={() => undefined}
            onSubmitAnswer={() => undefined}
            onSkipQuestion={() => undefined}
            onBackToReview={() => undefined}
            onSubmitQuiz={() => undefined}
            onReturnHome={() => undefined}
        />
    )
}

describe("StudentQuizView", () => {
    it("does not re-render the header and its timer while the student types", () => {
        const { rerender } = render(page("a"))
        rerender(page("ab"))
        rerender(page("abc"))

        expect(screen.getByText("answer: abc")).toBeInTheDocument()
        expect(timerRenders.count).toBe(1)
    })

    it("offers the skip only when the student may come back", () => {
        const { rerender } = render(
            page("", { allow_previous_questions: true })
        )
        expect(screen.getByText("skip offered")).toBeInTheDocument()

        rerender(page("", { allow_previous_questions: false }))
        expect(screen.queryByText("skip offered")).not.toBeInTheDocument()
    })

    it("leads back to the review once every question is answered or skipped", () => {
        const { rerender } = render(
            page("", {
                allow_answer_review: true,
                answered_question_numbers: [1, 2],
                skipped_question_numbers: [2],
            })
        )
        expect(
            screen.queryByRole("button", { name: /back-to-answer-review/ })
        ).not.toBeInTheDocument()

        rerender(
            page("", {
                allow_answer_review: true,
                answered_question_numbers: [1, 2],
                skipped_question_numbers: [3],
            })
        )
        expect(
            screen.getByRole("button", { name: /back-to-answer-review/ })
        ).toBeInTheDocument()
    })
})

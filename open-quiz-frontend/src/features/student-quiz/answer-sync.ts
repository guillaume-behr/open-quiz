import { trimTextBlock } from "@/lib/text-block"
import type { StudentQuizSession } from "@/api/types"

import type { EnteredAnswer } from "./use-deadline-submission"

/**
 * In an exam the student may go back in, the server holds what the screen
 * shows: the answer on screen is saved as it changes on a question already
 * handed in, and before leaving any question.
 */
export function savesAnswerOnScreen(session: StudentQuizSession): boolean {
    return (
        session.allow_previous_questions &&
        session.status === "in_progress" &&
        session.question != null
    )
}

/** Whether the question on screen was already answered or skipped. */
export function isHandedIn(session: StudentQuizSession): boolean {
    const questionNumber = session.question_number
    return (
        questionNumber != null &&
        (session.answered_question_numbers.includes(questionNumber) ||
            session.skipped_question_numbers.includes(questionNumber))
    )
}

/**
 * Whether the question on screen offers "Next question" rather than
 * submitting: a later question is already within reach. Only the last
 * question the student can reach (the last one not greyed out in the
 * navigation) keeps "Submit my answer", which moves them on, to the review,
 * or hands the paper in. Coming back from the review, the student goes
 * through the questions in order and reaches it again from the last one.
 */
export function offersNextQuestion(session: StudentQuizSession): boolean {
    const questionNumber = session.question_number
    return (
        savesAnswerOnScreen(session) &&
        questionNumber != null &&
        questionNumber < Math.max(0, ...session.accessible_question_numbers)
    )
}

/** Whether the answer on screen differs from the one the server holds. */
export function differsFromServer(
    session: StudentQuizSession,
    entered: EnteredAnswer
): boolean {
    const question = session.question
    if (!question) return false
    if (question.answer_mode === "written")
        // The server keeps the answer trimmed.
        return (
            trimTextBlock(entered.writtenAnswer) !==
            (session.written_answer ?? "")
        )
    const selected = new Set(entered.selectedChoiceIds)
    const saved = new Set(session.selected_choice_ids ?? [])
    return (
        selected.size !== saved.size ||
        [...selected].some((choiceId) => !saved.has(choiceId))
    )
}

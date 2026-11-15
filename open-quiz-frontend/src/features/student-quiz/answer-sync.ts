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
 * submitting: it is handed in already and is not the last one, whose
 * submission still hands the paper in or opens the review.
 */
export function offersNextQuestion(session: StudentQuizSession): boolean {
    return (
        savesAnswerOnScreen(session) &&
        isHandedIn(session) &&
        (session.question_number ?? 0) < session.total_questions
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
        return entered.writtenAnswer.trim() !== (session.written_answer ?? "")
    const selected = new Set(entered.selectedChoiceIds)
    const saved = new Set(session.selected_choice_ids ?? [])
    return (
        selected.size !== saved.size ||
        [...selected].some((choiceId) => !saved.has(choiceId))
    )
}

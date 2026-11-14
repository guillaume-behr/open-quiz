import { useEffect, useRef } from "react"

import type { StudentQuizSession } from "@/api/types"
import { millisecondsLeft, serverClockAnchor } from "@/lib/server-clock"

/**
 * How long before the deadline the answer on screen is sent: enough for the
 * request to reach the server, which refuses an answer once time is up.
 */
export const DEADLINE_SUBMISSION_LEAD_MS = 3_000

/** The answer entered on screen, as the question form holds it. */
export type EnteredAnswer = {
    selectedChoiceIds: string[]
    writtenAnswer: string
}

/**
 * Whether the answer on screen would be lost at the deadline: something is
 * entered, and the server does not hold it already.
 */
export function hasUnsentAnswer(
    session: StudentQuizSession,
    entered: EnteredAnswer
): boolean {
    const question = session.question
    if (!question) return false
    if (question.answer_mode === "written") {
        const written = entered.writtenAnswer.trim()
        return written !== "" && written !== (session.written_answer ?? "")
    }
    const selected = new Set(entered.selectedChoiceIds)
    const saved = new Set(session.selected_choice_ids ?? [])
    return (
        selected.size > 0 &&
        (selected.size !== saved.size ||
            [...selected].some((choiceId) => !saved.has(choiceId)))
    )
}

/**
 * Sends the answer on screen just before an exam's time runs out.
 *
 * The end of the session only keeps answers already validated: a long
 * written answer still being typed at 00:00 would be lost entirely, so it is
 * sent as it stands a few seconds before, as a paper is collected as it is.
 * `submit` is called only when there is something unsent and no other
 * request is under way.
 */
export function useDeadlineSubmission(
    session: StudentQuizSession | null,
    entered: EnteredAnswer,
    isBusy: boolean,
    submit: () => void
) {
    const latest = useRef({ session, entered, isBusy, submit })
    useEffect(() => {
        latest.current = { session, entered, isBusy, submit }
    })

    const endsAt =
        session?.status === "in_progress" && session.question
            ? session.ends_at
            : null
    const serverNow = session?.server_now
    const questionId = session?.question?.id
    useEffect(() => {
        if (!endsAt) return
        const delay =
            millisecondsLeft(endsAt, serverClockAnchor(serverNow)) -
            DEADLINE_SUBMISSION_LEAD_MS
        // Already past: the server has ended the exam, or is about to.
        if (delay <= -DEADLINE_SUBMISSION_LEAD_MS) return
        const timer = window.setTimeout(
            () => {
                const current = latest.current
                if (
                    !current.isBusy &&
                    current.session?.status === "in_progress" &&
                    current.session.question?.id === questionId &&
                    hasUnsentAnswer(current.session, current.entered)
                )
                    current.submit()
            },
            Math.max(0, delay)
        )
        return () => window.clearTimeout(timer)
    }, [endsAt, questionId, serverNow])
}

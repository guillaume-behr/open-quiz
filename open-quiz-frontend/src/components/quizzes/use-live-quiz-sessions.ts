import { ApiError } from "@/api/client"
import {
    cancelQuizSession,
    controlMakeupSession,
    deleteQuizSession,
    pauseQuizSession,
    resumeQuizSession,
    startQuizSession,
} from "@/api/quizzes"
import type { MakeupSession, QuizSession } from "@/api/types"
import { apiErrorMessage } from "@/lib/errors"
import { useTranslation } from "react-i18next"
import {
    type LiveSessionAction,
    type LiveSessions,
    useLiveSessions,
} from "./use-live-sessions"

export type LiveQuizSessions = LiveSessions<QuizSession>
export type LiveMakeupSessions = LiveSessions<MakeupSession>

const classSessionPath = (sessionId: number) =>
    `/api/quizzes/live/teacher/sessions/${sessionId}`

async function runClassAction(
    action: LiveSessionAction,
    session: QuizSession
): Promise<QuizSession | undefined> {
    switch (action) {
        case "start":
            return startQuizSession(session.id)
        case "pause":
            return pauseQuizSession(session.id)
        case "resume":
            return resumeQuizSession(session.id)
        case "cancel":
            await cancelQuizSession(session.id)
            return undefined
        case "delete":
            await deleteQuizSession(session.id)
            return undefined
        case "finish":
            throw new Error("A class session finishes when its time is up")
    }
}

async function runMakeupAction(
    action: LiveSessionAction,
    session: MakeupSession
): Promise<MakeupSession | undefined> {
    if (action === "delete") {
        throw new Error("A make-up session cannot be deleted")
    }
    return controlMakeupSession(session.id, action)
}

const isConflict = (caught: unknown) =>
    caught instanceof ApiError && caught.status === 409

/** The teacher's running class sessions and the one being supervised. */
export function useLiveQuizSessions(): LiveQuizSessions {
    const { t } = useTranslation()
    return useLiveSessions<QuizSession>({
        listPath: "/api/quizzes/live/teacher/sessions",
        sessionPath: classSessionPath,
        run: runClassAction,
        errorMessage: (action, caught) =>
            apiErrorMessage(
                caught,
                t,
                t(
                    action === "start"
                        ? "quiz-start-error"
                        : action === "delete"
                          ? "quiz-session-delete-error"
                          : action === "cancel" && isConflict(caught)
                            ? "quiz-cancel-with-answers-error"
                            : "quiz-session-action-error"
                )
            ),
    })
}

/** The teacher's running make-up sessions and the one being supervised. */
export function useLiveMakeupSessions(): LiveMakeupSessions {
    const { t } = useTranslation()
    return useLiveSessions<MakeupSession>({
        listPath: "/api/quizzes/live/teacher/makeup-sessions",
        run: runMakeupAction,
        errorMessage: (action, caught) =>
            apiErrorMessage(
                caught,
                t,
                t(
                    action === "cancel" && isConflict(caught)
                        ? "makeup-cancel-with-answers-error"
                        : "makeup-action-error"
                )
            ),
    })
}

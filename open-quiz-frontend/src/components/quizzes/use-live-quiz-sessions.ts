import { ApiError, getLiveAccessToken } from "@/api/client"
import {
    cancelQuizSession,
    deleteQuizSession,
    pauseQuizSession,
    resumeQuizSession,
    startQuizSession,
} from "@/api/quizzes"
import type { QuizSession } from "@/api/types"
import { isActiveSessionStatus } from "@/lib/session-status"
import { connectLiveUpdates } from "@/lib/live-updates"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { apiErrorMessage } from "@/lib/errors"

function isActiveSession(session: QuizSession): boolean {
    return isActiveSessionStatus(session.status)
}

export type LiveQuizSessions = ReturnType<typeof useLiveQuizSessions>

/**
 * The teacher's running sessions, kept current over live updates, and the
 * one opened in the supervision dialog with its start, pause, resume,
 * cancel and delete actions.
 */
export function useLiveQuizSessions() {
    const { t } = useTranslation()
    const [sessions, setSessions] = useState<QuizSession[]>([])
    const [liveSessionsLoadFailed, setLiveSessionsLoadFailed] = useState(false)
    const [activeSession, setActiveSession] = useState<QuizSession | null>(null)
    const [activeSessionError, setActiveSessionError] = useState<string | null>(
        null
    )
    const [isStarting, setIsStarting] = useState(false)
    const [sessionAction, setSessionAction] = useState<
        "pause" | "resume" | "cancel" | "delete" | null
    >(null)
    const [sessionActionToConfirm, setSessionActionToConfirm] = useState<
        "cancel" | "delete" | null
    >(null)
    // The session whose live updates are reconnecting, if any: a state left
    // by a session closed meanwhile does not show on the next one.
    const [reconnectingSessionId, setReconnectingSessionId] = useState<
        number | null
    >(null)
    const activeSessionId = activeSession?.id
    const activeSessionReconnecting =
        activeSessionId !== undefined &&
        reconnectingSessionId === activeSessionId

    useEffect(
        () =>
            connectLiveUpdates<QuizSession[]>({
                path: "/api/quizzes/live/teacher/sessions",
                getToken: getLiveAccessToken,
                onData: (updatedSessions) => {
                    const activeSessions =
                        updatedSessions.filter(isActiveSession)
                    setSessions(activeSessions)
                    setActiveSession((current) => {
                        if (!current) return null
                        return (
                            activeSessions.find(
                                (session) => session.id === current.id
                            ) ?? current
                        )
                    })
                    setLiveSessionsLoadFailed(false)
                },
                onUnavailable: () => setLiveSessionsLoadFailed(true),
            }),
        []
    )

    useEffect(() => {
        if (!activeSessionId) return
        // Keep one subscription for the lifetime of the dialog. Reconnecting
        // around every Start/Pause/Resume request creates a gap exactly while
        // the backend publishes the corresponding state change.
        return connectLiveUpdates<QuizSession>({
            path: `/api/quizzes/live/teacher/sessions/${activeSessionId}`,
            getToken: getLiveAccessToken,
            onData: (session) => {
                setActiveSessionError(null)
                setActiveSession(session)
                setSessions((current) =>
                    isActiveSession(session)
                        ? current.map((item) =>
                              item.id === session.id ? session : item
                          )
                        : current.filter((item) => item.id !== session.id)
                )
            },
            onDeleted: () => {
                setSessions((current) =>
                    current.filter((item) => item.id !== activeSessionId)
                )
                setActiveSession(null)
            },
            onUnavailable: () =>
                setActiveSessionError(t("quiz-session-refresh-error")),
            onConnectionChange: (state) =>
                setReconnectingSessionId(
                    state === "reconnecting" ? activeSessionId : null
                ),
        })
    }, [activeSessionId, t])

    async function handleStart(): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setIsStarting(true)
        try {
            const started = await startQuizSession(activeSession.id)
            setActiveSession(started)
            setSessions((current) =>
                current.map((session) =>
                    session.id === started.id ? started : session
                )
            )
        } catch (caught) {
            setActiveSessionError(
                apiErrorMessage(caught, t, t("quiz-start-error"))
            )
        } finally {
            setIsStarting(false)
        }
    }

    function updateSession(updated: QuizSession): void {
        setActiveSession(updated)
        setSessions((current) =>
            current.map((session) =>
                session.id === updated.id ? updated : session
            )
        )
    }

    async function handleSessionAction(
        action: "pause" | "resume" | "cancel"
    ): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setSessionAction(action)
        try {
            if (action === "cancel") {
                await cancelQuizSession(activeSession.id)
                setSessions((current) =>
                    current.filter((item) => item.id !== activeSession.id)
                )
                setActiveSession(null)
            } else {
                const updated =
                    action === "pause"
                        ? await pauseQuizSession(activeSession.id)
                        : await resumeQuizSession(activeSession.id)
                updateSession(updated)
            }
            setSessionActionToConfirm(null)
        } catch (caught) {
            setActiveSessionError(
                apiErrorMessage(
                    caught,
                    t,
                    caught instanceof ApiError && caught.status === 409
                        ? action === "cancel"
                            ? t("quiz-cancel-with-answers-error")
                            : t("quiz-session-action-error")
                        : t("quiz-session-action-error")
                )
            )
        } finally {
            setSessionAction(null)
        }
    }

    async function handleDeleteSession(): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setSessionAction("delete")
        try {
            await deleteQuizSession(activeSession.id)
            setSessions((current) =>
                current.filter((session) => session.id !== activeSession.id)
            )
            setSessionActionToConfirm(null)
            setActiveSession(null)
        } catch (caught) {
            setActiveSessionError(
                apiErrorMessage(caught, t, t("quiz-session-delete-error"))
            )
        } finally {
            setSessionAction(null)
        }
    }

    /** Show a session just launched, and open it for supervision. */
    function showLaunchedSession(session: QuizSession): void {
        setSessions((current) =>
            current.some((item) => item.id === session.id)
                ? current.map((item) =>
                      item.id === session.id ? session : item
                  )
                : [session, ...current]
        )
        openSession(session)
    }

    function openSession(session: QuizSession): void {
        setActiveSessionError(null)
        setActiveSession(session)
    }

    function closeSession(): void {
        setActiveSession(null)
        setActiveSessionError(null)
    }

    function askToConfirm(action: "cancel" | "delete"): void {
        setActiveSessionError(null)
        setSessionActionToConfirm(action)
    }

    return {
        sessions,
        liveSessionsLoadFailed,
        activeSession,
        activeSessionError,
        activeSessionReconnecting,
        isStarting,
        sessionAction,
        sessionActionToConfirm,
        setSessionActionToConfirm,
        showLaunchedSession,
        openSession,
        closeSession,
        askToConfirm,
        handleStart,
        handleSessionAction,
        handleDeleteSession,
    }
}

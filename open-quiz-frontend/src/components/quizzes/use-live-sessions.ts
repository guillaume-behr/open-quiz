import { getLiveAccessToken } from "@/api/client"
import type { MakeupSession, QuizSession } from "@/api/types"
import { connectLiveUpdates } from "@/lib/live-updates"
import { isActiveSessionStatus } from "@/lib/session-status"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

export type LiveSessionAction =
    "start" | "pause" | "resume" | "finish" | "cancel" | "delete"

/** The actions that ask the teacher to confirm before they run. */
export type ConfirmableSessionAction = "finish" | "cancel" | "delete"

export type LiveSession = QuizSession | MakeupSession

export type LiveSessionsConfig<S extends LiveSession> = {
    /** Live stream of the teacher's sessions of this kind. */
    listPath: string
    /** Live stream of one session, when the kind has one. */
    sessionPath?: (sessionId: number) => string
    /** Runs an action; resolves to the session as it now is, if it still exists. */
    run: (action: LiveSessionAction, session: S) => Promise<S | undefined>
    /** The message shown in the dialog when an action fails. */
    errorMessage: (action: LiveSessionAction, caught: unknown) => string
}

function isActiveSession(session: LiveSession): boolean {
    return isActiveSessionStatus(session.status)
}

export type LiveSessions<S extends LiveSession> = ReturnType<
    typeof useLiveSessions<S>
>

/**
 * The teacher's running sessions of one kind, kept current over live
 * updates, and the one opened in the supervision dialog with its actions:
 * which one is running, the error it left, and the one awaiting confirmation.
 */
export function useLiveSessions<S extends LiveSession>(
    config: LiveSessionsConfig<S>
) {
    const { t } = useTranslation()
    const { listPath, sessionPath } = config
    const [sessions, setSessions] = useState<S[]>([])
    const [liveSessionsLoadFailed, setLiveSessionsLoadFailed] = useState(false)
    const [activeSession, setActiveSession] = useState<S | null>(null)
    const [activeSessionError, setActiveSessionError] = useState<string | null>(
        null
    )
    const [sessionAction, setSessionAction] =
        useState<LiveSessionAction | null>(null)
    const [sessionActionToConfirm, setSessionActionToConfirm] =
        useState<ConfirmableSessionAction | null>(null)
    // The stream that is reconnecting, if any: the session's own stream by
    // its id, or the list stream (0) for a kind without one. A state left by
    // a session closed meanwhile does not show on the next one.
    const [reconnectingStreamId, setReconnectingStreamId] = useState<
        number | null
    >(null)
    const activeSessionId = activeSession?.id
    const activeSessionReconnecting =
        activeSessionId !== undefined &&
        reconnectingStreamId === (sessionPath ? activeSessionId : 0)

    useEffect(
        () =>
            connectLiveUpdates<S[]>({
                path: listPath,
                getToken: getLiveAccessToken,
                onData: (updatedSessions) => {
                    const activeSessions =
                        updatedSessions.filter(isActiveSession)
                    setSessions(activeSessions)
                    setActiveSession((current) => {
                        if (!current) return null
                        // Without a stream of its own, a session that left
                        // the list is over: its dialog closes.
                        return (
                            activeSessions.find(
                                (session) => session.id === current.id
                            ) ?? (sessionPath ? current : null)
                        )
                    })
                    setLiveSessionsLoadFailed(false)
                },
                onUnavailable: () => setLiveSessionsLoadFailed(true),
                onConnectionChange: sessionPath
                    ? undefined
                    : (state) =>
                          setReconnectingStreamId(
                              state === "reconnecting" ? 0 : null
                          ),
            }),
        [listPath, sessionPath]
    )

    useEffect(() => {
        if (!activeSessionId || !sessionPath) return
        // Keep one subscription for the lifetime of the dialog. Reconnecting
        // around every Start/Pause/Resume request creates a gap exactly while
        // the backend publishes the corresponding state change.
        return connectLiveUpdates<S>({
            path: sessionPath(activeSessionId),
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
                setReconnectingStreamId(
                    state === "reconnecting" ? activeSessionId : null
                ),
        })
    }, [activeSessionId, sessionPath, t])

    async function runAction(action: LiveSessionAction): Promise<void> {
        if (!activeSession || sessionAction !== null) return
        const session = activeSession
        setActiveSessionError(null)
        setSessionAction(action)
        try {
            const updated = await config.run(action, session)
            if (updated && isActiveSession(updated)) {
                setActiveSession(updated)
                setSessions((current) =>
                    current.map((item) =>
                        item.id === updated.id ? updated : item
                    )
                )
            } else {
                setSessions((current) =>
                    current.filter((item) => item.id !== session.id)
                )
                setActiveSession(null)
            }
            setSessionActionToConfirm(null)
        } catch (caught) {
            setActiveSessionError(config.errorMessage(action, caught))
        } finally {
            setSessionAction(null)
        }
    }

    /** Show a session just launched, and open it for supervision. */
    function showLaunchedSession(session: S): void {
        setSessions((current) =>
            current.some((item) => item.id === session.id)
                ? current.map((item) =>
                      item.id === session.id ? session : item
                  )
                : [session, ...current]
        )
        openSession(session)
    }

    function openSession(session: S): void {
        setActiveSessionError(null)
        setActiveSession(session)
    }

    function closeSession(): void {
        setActiveSession(null)
        setActiveSessionError(null)
    }

    function askToConfirm(action: ConfirmableSessionAction): void {
        setActiveSessionError(null)
        setSessionActionToConfirm(action)
    }

    return {
        sessions,
        liveSessionsLoadFailed,
        activeSession,
        activeSessionError,
        activeSessionReconnecting,
        sessionAction,
        sessionActionToConfirm,
        setSessionActionToConfirm,
        showLaunchedSession,
        openSession,
        closeSession,
        askToConfirm,
        runAction,
    }
}

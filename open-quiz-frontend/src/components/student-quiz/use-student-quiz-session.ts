import { type FormEvent, useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

import { ApiError } from "@/api/client"
import {
    getStudentQuizSession,
    joinQuiz,
    leaveStudentQuiz,
    navigateStudentQuiz,
    reviewStudentAnswers,
    submitStudentQuiz,
    skipStudentQuestion,
    submitStudentQuizAnswer,
} from "@/api/quizzes"
import { StudentQuizSessionSchema } from "@/api/schemas"
import type { StudentQuizSession } from "@/api/types"
import { apiErrorMessage } from "@/lib/errors"
import { connectLiveUpdates } from "@/lib/live-updates"

import { removeDrafts } from "./answer-drafts"
import {
    clearStoredQuizSession,
    readStoredQuizSession,
    storeQuizSession,
} from "./student-quiz-session"
import { useAnswerDrafts } from "./use-answer-drafts"

/**
 * A student's exam participation: the session restored from this tab, its
 * live updates, the answer being entered, and the requests that move through
 * the exam (join, navigate, answer, hand in, leave).
 */
export function useStudentQuizSession(
    studentToken: string,
    onSessionCleared?: () => void
) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [restoredSession] = useState(readStoredQuizSession)
    const [joinCode, setJoinCode] = useState(restoredSession?.joinCode ?? "")
    const [participantToken, setParticipantToken] = useState<string | null>(
        restoredSession?.participantToken ?? null
    )
    const [session, setSession] = useState<StudentQuizSession | null>(null)
    const [selectedChoiceIds, setSelectedChoiceIds] = useState<string[]>([])
    const [writtenAnswer, setWrittenAnswer] = useState("")
    const [isBusy, setIsBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const isLeavingQuiz = useRef(false)
    const sessionRequestVersion = useRef(0)
    const liveSessionRef = useRef<StudentQuizSession | null>(session)
    const liveRevisionRef = useRef(0)
    // What the student has entered on each question they visited, so that
    // stepping back to an earlier question, or reloading the tab, does not
    // throw away an answer that is not submitted yet.
    const drafts = useAnswerDrafts(
        session?.join_code ?? restoredSession?.joinCode ?? null
    )
    const draftedQuestionIdRef = useRef<number | null>(null)

    const liveJoinCode = session?.join_code
    const isSessionOver = ["finished", "cancelled"].includes(
        session?.status ?? ""
    )
    const liveConnection =
        liveJoinCode && participantToken && !isSessionOver
            ? `${liveJoinCode}:${participantToken}`
            : null
    // Which connection is reconnecting: a state left by an earlier one is
    // ignored rather than reset from the effect.
    const [reconnectingConnection, setReconnectingConnection] = useState<
        string | null
    >(null)
    const liveReconnecting =
        liveConnection !== null && reconnectingConnection === liveConnection

    // Show the question being opened with the draft kept for it, and fall back
    // to the answer already recorded by the server when there is none. An
    // empty draft is a draft: an answer the student cleared stays cleared.
    const applyAnswerState = useCallback(
        (updated: StudentQuizSession) => {
            const questionId = updated.question?.id ?? null
            draftedQuestionIdRef.current = questionId
            const draft =
                questionId === null ? undefined : drafts.getDraft(questionId)
            setSelectedChoiceIds(
                draft !== undefined
                    ? draft.selectedChoiceIds
                    : (updated.selected_choice_ids ?? [])
            )
            setWrittenAnswer(
                draft !== undefined
                    ? draft.writtenAnswer
                    : (updated.written_answer ?? "")
            )
        },
        [drafts]
    )

    const applySession = useCallback(
        (updated: StudentQuizSession) => {
            setSession(updated)
            applyAnswerState(updated)
        },
        [applyAnswerState]
    )

    useEffect(() => {
        liveSessionRef.current = session
    }, [session])

    useEffect(() => {
        const questionId = draftedQuestionIdRef.current
        if (questionId === null) return
        drafts.setDraft(questionId, { selectedChoiceIds, writtenAnswer })
    }, [drafts, selectedChoiceIds, writtenAnswer])

    // A handed-in or ended exam keeps no draft in this browser.
    const sessionStatus = session?.status
    useEffect(() => {
        if (sessionStatus === "finished" || sessionStatus === "cancelled")
            drafts.clearAll()
    }, [drafts, sessionStatus])

    useEffect(() => {
        if (!restoredSession) return

        let active = true
        const requestVersion = sessionRequestVersion.current
        void getStudentQuizSession(
            restoredSession.joinCode,
            restoredSession.participantToken
        )
            .then((restoredState) => {
                if (active && requestVersion === sessionRequestVersion.current)
                    applySession(restoredState)
            })
            .catch((restoreError: unknown) => {
                if (!active || requestVersion !== sessionRequestVersion.current)
                    return
                // The exam was taken back in another window: this tab says
                // so and stays here, rather than suggest the session is gone.
                const resumedElsewhere =
                    restoreError instanceof ApiError &&
                    restoreError.code === "QUIZ_PARTICIPANT_SESSION_RESUMED"
                if (
                    restoreError instanceof ApiError &&
                    [401, 403, 404].includes(restoreError.status)
                ) {
                    clearStoredQuizSession()
                    setParticipantToken(null)
                    if (!resumedElsewhere) onSessionCleared?.()
                }
                setError(
                    resumedElsewhere
                        ? apiErrorMessage(restoreError, t, "")
                        : t("student-session-restore-error")
                )
            })
        return () => {
            active = false
        }
    }, [applySession, onSessionCleared, restoredSession, t])

    useEffect(() => {
        // A finished session sends nothing more: close its connection.
        if (!liveJoinCode || !participantToken || isSessionOver) return
        const connection = `${liveJoinCode}:${participantToken}`

        return connectLiveUpdates({
            path: `/api/quizzes/live/student/sessions/${encodeURIComponent(liveJoinCode)}`,
            getToken: () => Promise.resolve(participantToken),
            schema: StudentQuizSessionSchema,
            onData: (updated) => {
                liveRevisionRef.current += 1
                setError(null)
                const current = liveSessionRef.current
                if (
                    updated.question &&
                    updated.question.id !== current?.question?.id &&
                    current?.status !== "paused"
                )
                    applyAnswerState(updated)
                const next =
                    current?.question &&
                    current.question.id === updated.question?.id
                        ? { ...updated, question: current.question }
                        : updated
                liveSessionRef.current = next
                setSession(next)
            },
            onUnavailable: () => setError(t("student-session-error")),
            onConnectionChange: (state) =>
                setReconnectingConnection(
                    state === "reconnecting" ? connection : null
                ),
        })
    }, [applyAnswerState, isSessionOver, liveJoinCode, participantToken, t])

    // One request moving through the exam: a reply that arrives after a live
    // update is dropped, since the live state is newer.
    async function runSessionRequest(
        request: () => Promise<StudentQuizSession>,
        errorKey: string,
        onError?: (caught: unknown) => Promise<void>
    ) {
        setIsBusy(true)
        sessionRequestVersion.current += 1
        const liveRevision = liveRevisionRef.current
        try {
            const updated = await request()
            if (liveRevisionRef.current === liveRevision) applySession(updated)
        } catch (caught) {
            setError(apiErrorMessage(caught, t, t(errorKey)))
            await onError?.(caught)
        } finally {
            setIsBusy(false)
        }
    }

    async function join(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setError(null)
        setIsBusy(true)
        sessionRequestVersion.current += 1
        try {
            const joined = await joinQuiz(joinCode.trim(), studentToken)
            const { participant_token, ...state } = joined
            storeQuizSession({
                joinCode: state.join_code,
                participantToken: participant_token,
            })
            // Drafts left in this tab by an earlier participation, perhaps
            // another student's, never show in this one.
            removeDrafts(state.join_code)
            setParticipantToken(participant_token)
            applySession(state)
        } catch (caught) {
            setError(apiErrorMessage(caught, t, t("join-quiz-error")))
        } finally {
            setIsBusy(false)
        }
    }

    /** Leaves the exam; `resetView` clears what the page derived from it. */
    async function leave(resetView: () => void) {
        if (!session || !participantToken) return
        isLeavingQuiz.current = true
        sessionRequestVersion.current += 1
        setIsBusy(true)
        setError(null)
        try {
            await leaveStudentQuiz(session.join_code, participantToken)
        } catch (caught) {
            isLeavingQuiz.current = false
            setIsBusy(false)
            setError(apiErrorMessage(caught, t, t("student-session-error")))
            return
        }
        clearStoredQuizSession()
        drafts.clearAll()
        draftedQuestionIdRef.current = null
        setSession(null)
        setParticipantToken(null)
        setJoinCode("")
        setSelectedChoiceIds([])
        setWrittenAnswer("")
        setError(null)
        setIsBusy(false)
        resetView()
        onSessionCleared?.()
        if (["finished", "cancelled"].includes(session.status))
            void navigate("/student/dashboard")

        if (document.fullscreenElement) {
            void document
                .exitFullscreen()
                .then(releaseLeavingState, releaseLeavingState)
        } else {
            releaseLeavingState()
        }
    }

    function releaseLeavingState() {
        window.setTimeout(() => {
            isLeavingQuiz.current = false
        }, 0)
    }

    async function goToQuestion(questionNumber: number) {
        if (
            !session ||
            !participantToken ||
            !session.accessible_question_numbers.includes(questionNumber)
        )
            return
        const { join_code } = session
        await runSessionRequest(
            () =>
                navigateStudentQuiz(
                    join_code,
                    participantToken,
                    questionNumber
                ),
            "student-navigation-error"
        )
    }

    async function backToReview() {
        if (!session || !participantToken) return
        const { join_code } = session
        setError(null)
        await runSessionRequest(
            () => reviewStudentAnswers(join_code, participantToken),
            "student-navigation-error"
        )
    }

    async function submitQuiz() {
        if (!session || !participantToken) return
        const { join_code } = session
        setError(null)
        await runSessionRequest(async () => {
            const updated = await submitStudentQuiz(join_code, participantToken)
            // The paper is handed in: nothing is left to draft.
            drafts.clearAll()
            return updated
        }, "student-submit-quiz-error")
    }

    async function submitAnswer(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!session?.question || !participantToken) return
        const { join_code, question } = session
        setError(null)
        await runSessionRequest(
            async () => {
                const updated = await submitStudentQuizAnswer(
                    join_code,
                    participantToken,
                    {
                        question_id: question.id,
                        selected_choice_ids:
                            question.answer_mode === "written"
                                ? undefined
                                : selectedChoiceIds,
                        written_answer:
                            question.answer_mode === "written"
                                ? writtenAnswer
                                : undefined,
                    }
                )
                // The server now holds this answer: coming back to the
                // question must show what was submitted, not a stale draft.
                drafts.clearDraft(question.id)
                return updated
            },
            "student-answer-error",
            (caught) => showServerQuestionOnMismatch(caught, join_code)
        )
    }

    async function skipQuestion() {
        if (!session?.question || !participantToken) return
        const { join_code, question } = session
        setError(null)
        // What the student entered stays a draft of the question: skipping it
        // to come back later must not lose it.
        await runSessionRequest(
            () => skipStudentQuestion(join_code, participantToken, question.id),
            "student-answer-error",
            (caught) => showServerQuestionOnMismatch(caught, join_code)
        )
    }

    // The page showed another question than the server's current one: show
    // the right one. What the student entered stays a draft of its question.
    async function showServerQuestionOnMismatch(
        caught: unknown,
        joinCode: string
    ) {
        if (
            !participantToken ||
            !(caught instanceof ApiError) ||
            caught.code !== "ANSWER_QUESTION_MISMATCH"
        )
            return
        try {
            applySession(
                await getStudentQuizSession(joinCode, participantToken)
            )
        } catch {
            // The message above already asks to try again.
        }
    }

    function updateJoinCode(value: string) {
        setJoinCode(value)
        setError(null)
    }

    return {
        joinCode,
        updateJoinCode,
        participantToken,
        session,
        selectedChoiceIds,
        setSelectedChoiceIds,
        writtenAnswer,
        setWrittenAnswer,
        isBusy,
        error,
        setError,
        liveReconnecting,
        isLeavingQuiz,
        join,
        leave,
        goToQuestion,
        backToReview,
        submitQuiz,
        submitAnswer,
        skipQuestion,
    }
}

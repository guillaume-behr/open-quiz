import { ApiError } from "@/api/client"
import { isRtlLanguage } from "@/lib/utils"
import {
    getStudentQuizSession,
    joinQuiz,
    leaveStudentQuiz,
    navigateStudentQuiz,
    reviewStudentAnswers,
    submitStudentQuiz,
    submitStudentQuizAnswer,
} from "@/api/quizzes"
import type { StudentQuizSession } from "@/api/types"
import { JoinQuizForm } from "@/components/forms/join-quiz-form"
import { NavbarAction } from "@/components/navigation/navbar-action"
import { isActiveSessionStatus } from "@/lib/session-status"
import { connectLiveUpdates } from "@/lib/live-updates"
import { Button } from "@/components/ui/button"
import { LogOut } from "lucide-react"
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"
import { FullscreenPrompt } from "./fullscreen-prompt"
import {
    clearStoredQuizSession,
    readStoredQuizSession,
    storeQuizSession,
} from "./student-quiz-session"
import { StudentQuizPage } from "./student-quiz-page"
import { useQuizMonitoring } from "./use-quiz-monitoring"
import { useQuizTranslation } from "./use-quiz-translation"

type AnswerDraft = {
    selectedChoiceIds: number[]
    writtenAnswer: string
}

export function StudentQuiz({
    studentToken,
    onSessionCleared,
}: {
    studentToken: string
    onSessionCleared?: () => void
}) {
    const { t, i18n } = useTranslation()
    const navigate = useNavigate()
    const [restoredSession] = useState(readStoredQuizSession)
    const [joinCode, setJoinCode] = useState(restoredSession?.joinCode ?? "")
    const [participantToken, setParticipantToken] = useState<string | null>(
        restoredSession?.participantToken ?? null
    )
    const [session, setSession] = useState<StudentQuizSession | null>(null)
    const [selectedChoiceIds, setSelectedChoiceIds] = useState<number[]>([])
    const [writtenAnswer, setWrittenAnswer] = useState("")
    const [isBusy, setIsBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const isLeavingQuiz = useRef(false)
    const sessionRequestVersion = useRef(0)
    const liveSessionRef = useRef<StudentQuizSession | null>(session)
    const liveRevisionRef = useRef(0)
    // What the student has entered on each question they visited, so that
    // stepping back to an earlier question and returning does not throw away
    // an answer that is not submitted yet.
    const answerDraftsRef = useRef(new Map<number, AnswerDraft>())
    const draftedQuestionIdRef = useRef<number | null>(null)
    const { isFullscreen, enterFullscreen } = useQuizMonitoring(
        session,
        participantToken,
        isLeavingQuiz
    )
    const translation = useQuizTranslation(session, i18n)

    const contentDirection =
        session == null || translation.viewState.active
            ? isRtlLanguage(i18n.resolvedLanguage)
                ? "rtl"
                : "ltr"
            : isRtlLanguage(session.source_language)
              ? "rtl"
              : "ltr"
    const liveJoinCode = session?.join_code

    // Show the question being opened with the draft kept for it, and fall back
    // to the answer already recorded by the server when there is none.
    const applyAnswerState = useCallback((updated: StudentQuizSession) => {
        const questionId = updated.question?.id ?? null
        draftedQuestionIdRef.current = questionId
        const draft =
            questionId === null
                ? undefined
                : answerDraftsRef.current.get(questionId)
        setSelectedChoiceIds(
            draft?.selectedChoiceIds.length
                ? draft.selectedChoiceIds
                : (updated.selected_choice_ids ?? [])
        )
        setWrittenAnswer(
            draft?.writtenAnswer
                ? draft.writtenAnswer
                : (updated.written_answer ?? "")
        )
    }, [])

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
        answerDraftsRef.current.set(questionId, {
            selectedChoiceIds,
            writtenAnswer,
        })
    }, [selectedChoiceIds, writtenAnswer])

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
                if (
                    restoreError instanceof ApiError &&
                    [401, 403, 404].includes(restoreError.status)
                ) {
                    clearStoredQuizSession()
                    setParticipantToken(null)
                    onSessionCleared?.()
                }
                setError(t("student-session-restore-error"))
            })
        return () => {
            active = false
        }
    }, [applySession, onSessionCleared, restoredSession, t])

    useEffect(() => {
        if (
            !liveJoinCode ||
            !participantToken ||
            ["finished", "cancelled"].includes(
                liveSessionRef.current?.status ?? ""
            )
        )
            return

        return connectLiveUpdates<StudentQuizSession>({
            path: `/api/quizzes/live/student/sessions/${encodeURIComponent(liveJoinCode)}`,
            getToken: async () => participantToken,
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
        })
    }, [applyAnswerState, liveJoinCode, participantToken, t])

    async function handleJoin(event: FormEvent<HTMLFormElement>) {
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
            setParticipantToken(participant_token)
            applySession(state)
        } catch {
            setError(t("join-quiz-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function leaveQuiz() {
        if (!session || !participantToken) return
        isLeavingQuiz.current = true
        sessionRequestVersion.current += 1
        setIsBusy(true)
        setError(null)
        try {
            await leaveStudentQuiz(session.join_code, participantToken)
        } catch {
            isLeavingQuiz.current = false
            setIsBusy(false)
            setError(t("student-session-error"))
            return
        }
        clearStoredQuizSession()
        answerDraftsRef.current.clear()
        draftedQuestionIdRef.current = null
        setSession(null)
        setParticipantToken(null)
        setJoinCode("")
        setSelectedChoiceIds([])
        setWrittenAnswer("")
        setError(null)
        setIsBusy(false)
        translation.reset()
        onSessionCleared?.()
        if (["finished", "cancelled"].includes(session.status))
            navigate("/student/dashboard")

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

        setIsBusy(true)
        sessionRequestVersion.current += 1
        const liveRevision = liveRevisionRef.current
        try {
            const updated = await navigateStudentQuiz(
                session.join_code,
                participantToken,
                questionNumber
            )
            if (liveRevisionRef.current === liveRevision) applySession(updated)
        } catch {
            setError(t("student-navigation-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function backToReview() {
        if (!session || !participantToken) return

        setError(null)
        setIsBusy(true)
        sessionRequestVersion.current += 1
        const liveRevision = liveRevisionRef.current
        try {
            const updated = await reviewStudentAnswers(
                session.join_code,
                participantToken
            )
            if (liveRevisionRef.current === liveRevision) applySession(updated)
        } catch {
            setError(t("student-navigation-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function submitQuiz() {
        if (!session || !participantToken) return

        setError(null)
        setIsBusy(true)
        sessionRequestVersion.current += 1
        const liveRevision = liveRevisionRef.current
        try {
            const updated = await submitStudentQuiz(
                session.join_code,
                participantToken
            )
            if (liveRevisionRef.current === liveRevision) applySession(updated)
        } catch {
            setError(t("student-submit-quiz-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function handleAnswer(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!session?.question || !participantToken) return

        setError(null)
        setIsBusy(true)
        sessionRequestVersion.current += 1
        const liveRevision = liveRevisionRef.current
        const answeredQuestionId = session.question.id
        try {
            const updated = await submitStudentQuizAnswer(
                session.join_code,
                participantToken,
                {
                    selected_choice_ids:
                        session.question.answer_mode === "written"
                            ? undefined
                            : selectedChoiceIds,
                    written_answer:
                        session.question.answer_mode === "written"
                            ? writtenAnswer
                            : undefined,
                }
            )
            // The server now holds this answer: coming back to the question
            // must show what was submitted, not a stale draft.
            answerDraftsRef.current.delete(answeredQuestionId)
            if (liveRevisionRef.current === liveRevision) applySession(updated)
        } catch {
            setError(t("student-answer-error"))
        } finally {
            setIsBusy(false)
        }
    }

    function updateJoinCode(value: string) {
        setJoinCode(value)
        setError(null)
    }

    if (!session || !participantToken) {
        return (
            <JoinQuizForm
                joinCode={joinCode}
                isBusy={isBusy}
                error={error}
                onJoinCodeChange={updateJoinCode}
                onSubmit={handleJoin}
            />
        )
    }

    const requiresFullscreen = isActiveSessionStatus(session.status)

    if (!isFullscreen && requiresFullscreen) {
        return (
            <>
                <QuizNavbarAction
                    disabled={isBusy}
                    finished={false}
                    onLeave={() => void leaveQuiz()}
                />
                <FullscreenPrompt
                    studentName={session.student_name}
                    error={error}
                    onEnterFullscreen={() => {
                        void enterFullscreen().catch(() =>
                            setError(t("student-session-error"))
                        )
                    }}
                />
            </>
        )
    }

    return (
        <>
            <QuizNavbarAction
                disabled={isBusy}
                finished={["cancelled", "finished"].includes(session.status)}
                onLeave={() => void leaveQuiz()}
            />
            <StudentQuizPage
                session={{
                    ...session,
                    answer_summaries: translation.answerSummaries,
                }}
                question={translation.question}
                participantToken={participantToken}
                title={translation.title}
                contentDirection={contentDirection}
                selectedChoiceIds={selectedChoiceIds}
                writtenAnswer={writtenAnswer}
                isBusy={isBusy}
                error={error}
                translation={translation.viewState}
                onToggleTranslation={() => void translation.toggle()}
                onSelectedChoiceIdsChange={setSelectedChoiceIds}
                onWrittenAnswerChange={setWrittenAnswer}
                onNavigate={(questionNumber) =>
                    void goToQuestion(questionNumber)
                }
                onSubmitAnswer={handleAnswer}
                onBackToReview={() => void backToReview()}
                onSubmitQuiz={() => void submitQuiz()}
                onReturnHome={() => void leaveQuiz()}
            />
        </>
    )
}

function QuizNavbarAction({
    disabled,
    finished,
    onLeave,
}: {
    disabled: boolean
    finished: boolean
    onLeave: () => void
}) {
    const { t } = useTranslation()
    return (
        <NavbarAction>
            <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={disabled}
                onClick={onLeave}
            >
                <LogOut />
                {t(finished ? "join-another-quiz" : "leave-quiz")}
            </Button>
        </NavbarAction>
    )
}

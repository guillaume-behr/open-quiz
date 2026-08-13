import { ApiError } from "@/api/client"
import { isRtlLanguage } from "@/lib/utils"
import {
    getStudentQuizSession,
    joinQuiz,
    leaveStudentQuiz,
    navigateStudentQuiz,
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

    const applySession = useCallback((updated: StudentQuizSession) => {
        setSession(updated)
        setSelectedChoiceIds(updated.selected_choice_ids ?? [])
        setWrittenAnswer(updated.written_answer ?? "")
    }, [])

    useEffect(() => {
        liveSessionRef.current = session
    }, [session])

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
                ) {
                    setSelectedChoiceIds(updated.selected_choice_ids ?? [])
                    setWrittenAnswer(updated.written_answer ?? "")
                }
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
    }, [liveJoinCode, participantToken, t])

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

    async function handleAnswer(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!session?.question || !participantToken) return

        setError(null)
        setIsBusy(true)
        sessionRequestVersion.current += 1
        const liveRevision = liveRevisionRef.current
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
            setSelectedChoiceIds([])
            setWrittenAnswer("")
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
                session={session}
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

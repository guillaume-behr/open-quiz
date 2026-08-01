import { ApiError } from "@/api/client"
import {
    getStudentQuizSession,
    joinQuiz,
    navigateStudentQuiz,
    submitStudentQuizAnswer,
} from "@/api/quizzes"
import type { StudentQuizSession } from "@/api/types"
import { JoinQuizForm } from "@/components/forms/join-quiz-form"
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { FullscreenPrompt } from "./fullscreen-prompt"
import {
    clearStoredQuizSession,
    readStoredQuizSession,
    storeQuizSession,
} from "./student-quiz-session"
import { StudentQuizPage } from "./student-quiz-page"
import { useQuizMonitoring } from "./use-quiz-monitoring"
import { useQuizTranslation } from "./use-quiz-translation"

export function StudentQuiz() {
    const { t, i18n } = useTranslation()
    const [restoredSession] = useState(readStoredQuizSession)
    const [studentIdentifier, setStudentIdentifier] = useState(
        restoredSession?.studentIdentifier ?? ""
    )
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
    const { isFullscreen, enterFullscreen } = useQuizMonitoring(
        session,
        participantToken,
        isLeavingQuiz
    )
    const translation = useQuizTranslation(session, i18n)

    const applySession = useCallback((updated: StudentQuizSession) => {
        setSession(updated)
        setSelectedChoiceIds(updated.selected_choice_ids ?? [])
        setWrittenAnswer(updated.written_answer ?? "")
    }, [])

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
                }
                setError(t("student-session-restore-error"))
            })
        return () => {
            active = false
        }
    }, [applySession, restoredSession, t])

    useEffect(() => {
        if (
            !session ||
            !participantToken ||
            isBusy ||
            ["finished", "cancelled"].includes(session.status)
        )
            return

        let active = true
        let refreshInFlight = false
        const refresh = () => {
            if (refreshInFlight) return
            refreshInFlight = true
            const requestVersion = sessionRequestVersion.current
            void getStudentQuizSession(session.join_code, participantToken)
                .then((updated) => {
                    if (
                        !active ||
                        requestVersion !== sessionRequestVersion.current
                    )
                        return
                    if (
                        updated.question &&
                        updated.question.id !== session.question?.id &&
                        session.status !== "paused"
                    ) {
                        setSelectedChoiceIds(updated.selected_choice_ids ?? [])
                        setWrittenAnswer(updated.written_answer ?? "")
                    }
                    setSession((current) => {
                        const currentQuestion = current?.question
                        return currentQuestion &&
                            currentQuestion.id === updated.question?.id
                            ? { ...updated, question: currentQuestion }
                            : updated
                    })
                })
                .catch(() => {
                    if (
                        active &&
                        requestVersion === sessionRequestVersion.current
                    )
                        setError(t("student-session-error"))
                })
                .finally(() => {
                    refreshInFlight = false
                })
        }
        const interval = window.setInterval(refresh, 1500)
        return () => {
            active = false
            window.clearInterval(interval)
        }
    }, [isBusy, participantToken, session, t])

    async function handleJoin(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setError(null)
        setIsBusy(true)
        sessionRequestVersion.current += 1
        try {
            const joined = await joinQuiz(
                joinCode.trim(),
                studentIdentifier.trim()
            )
            const { participant_token, ...state } = joined
            storeQuizSession({
                joinCode: state.join_code,
                studentIdentifier: studentIdentifier.trim(),
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

    function leaveQuiz() {
        isLeavingQuiz.current = true
        sessionRequestVersion.current += 1
        clearStoredQuizSession()
        setSession(null)
        setParticipantToken(null)
        setJoinCode("")
        setSelectedChoiceIds([])
        setWrittenAnswer("")
        setError(null)
        translation.reset()

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

    async function goToPreviousQuestion() {
        if (
            !session ||
            !participantToken ||
            !session.question_number ||
            session.question_number <= 1
        )
            return

        setIsBusy(true)
        sessionRequestVersion.current += 1
        try {
            const updated = await navigateStudentQuiz(
                session.join_code,
                participantToken,
                session.question_number - 1
            )
            applySession(updated)
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
            setSession(updated)
        } catch {
            setError(t("student-answer-error"))
        } finally {
            setIsBusy(false)
        }
    }

    function updateStudentIdentifier(value: string) {
        setStudentIdentifier(value)
        setError(null)
    }

    function updateJoinCode(value: string) {
        setJoinCode(value)
        setError(null)
    }

    if (!session || !participantToken) {
        return (
            <JoinQuizForm
                studentIdentifier={studentIdentifier}
                joinCode={joinCode}
                isBusy={isBusy}
                error={error}
                onStudentIdentifierChange={updateStudentIdentifier}
                onJoinCodeChange={updateJoinCode}
                onSubmit={handleJoin}
            />
        )
    }

    if (!isFullscreen && !["finished", "cancelled"].includes(session.status)) {
        return (
            <FullscreenPrompt
                studentName={session.student_name}
                error={error}
                onEnterFullscreen={() => {
                    void enterFullscreen().catch(() =>
                        setError(t("student-session-error"))
                    )
                }}
                onLeave={leaveQuiz}
            />
        )
    }

    return (
        <StudentQuizPage
            session={session}
            question={translation.question}
            participantToken={participantToken}
            title={translation.title}
            selectedChoiceIds={selectedChoiceIds}
            writtenAnswer={writtenAnswer}
            isBusy={isBusy}
            error={error}
            translation={translation.viewState}
            onToggleTranslation={() => void translation.toggle()}
            onSelectedChoiceIdsChange={setSelectedChoiceIds}
            onWrittenAnswerChange={setWrittenAnswer}
            onPrevious={() => void goToPreviousQuestion()}
            onSubmitAnswer={handleAnswer}
            onLeave={leaveQuiz}
        />
    )
}

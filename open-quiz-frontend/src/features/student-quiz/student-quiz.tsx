import { isRtlLanguage } from "@/lib/utils"
import { JoinQuizForm } from "@/components/forms/join-quiz-form"
import { NavbarAction } from "@/components/navigation/navbar-action"
import { isActiveSessionStatus } from "@/lib/session-status"
import { Button } from "@/components/ui/button"
import { LogOut } from "lucide-react"
import { useMemo } from "react"
import { useTranslation } from "react-i18next"
import { FullscreenPrompt } from "./fullscreen-prompt"
import { StudentQuizView } from "./student-quiz-view"
import { useQuizMonitoring } from "./use-quiz-monitoring"
import { useQuizTranslation } from "./use-quiz-translation"
import { useStudentQuizSession } from "./use-student-quiz-session"

export function StudentQuiz({
    studentToken,
    onSessionCleared,
}: {
    studentToken: string
    onSessionCleared?: () => void
}) {
    const { t, i18n } = useTranslation()
    const quiz = useStudentQuizSession(studentToken, onSessionCleared)
    const { session, participantToken, isBusy, error, setError } = quiz
    const { isFullscreen, enterFullscreen } = useQuizMonitoring(
        session,
        participantToken,
        quiz.isLeavingQuiz
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

    function leaveQuiz() {
        void quiz.leave(translation.reset)
    }

    // Kept across keystrokes, so that what only reads the session (the header
    // and its timer) does not re-render while the student types.
    const answerSummaries = translation.answerSummaries
    const pageSession = useMemo(
        () => session && { ...session, answer_summaries: answerSummaries },
        [session, answerSummaries]
    )

    if (!session || !pageSession || !participantToken) {
        return (
            <JoinQuizForm
                joinCode={quiz.joinCode}
                isBusy={isBusy}
                error={error}
                onJoinCodeChange={quiz.updateJoinCode}
                onSubmit={(event) => void quiz.join(event)}
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
                    onLeave={leaveQuiz}
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
                onLeave={leaveQuiz}
            />
            <StudentQuizView
                session={pageSession}
                question={translation.question}
                participantToken={participantToken}
                title={translation.title}
                liveReconnecting={quiz.liveReconnecting}
                contentDirection={contentDirection}
                selectedChoiceIds={quiz.selectedChoiceIds}
                writtenAnswer={quiz.writtenAnswer}
                isBusy={isBusy}
                error={error}
                translation={translation.viewState}
                onToggleTranslation={() => void translation.toggle()}
                onSelectedChoiceIdsChange={quiz.setSelectedChoiceIds}
                onWrittenAnswerChange={quiz.setWrittenAnswer}
                onNavigate={(questionNumber) =>
                    void quiz.goToQuestion(questionNumber)
                }
                onSubmitAnswer={(event) => void quiz.submitAnswer(event)}
                onSkipQuestion={() => void quiz.skipQuestion()}
                onBackToReview={() => void quiz.backToReview()}
                onSubmitQuiz={() => void quiz.submitQuiz()}
                onReturnHome={leaveQuiz}
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

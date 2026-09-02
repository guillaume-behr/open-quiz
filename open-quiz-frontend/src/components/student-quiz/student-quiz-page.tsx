import type { StudentQuizQuestion, StudentQuizSession } from "@/api/types"
import { QuizTimer } from "@/components/quizzes/quiz-timer"
import { Button } from "@/components/ui/button"
import { ListChecks, LoaderCircle } from "lucide-react"
import type { FormEvent } from "react"
import { useTranslation } from "react-i18next"
import { AnswerReview } from "./answer-review"
import { StudentNameBadge } from "./fullscreen-prompt"
import { StudentQuestionForm } from "./student-question-form"
import {
    TranslationNotice,
    type TranslationViewState,
} from "./translation-notice"

type StudentQuizPageProps = {
    session: StudentQuizSession
    question: StudentQuizQuestion | null
    participantToken: string
    title: string
    contentDirection: "ltr" | "rtl"
    selectedChoiceIds: number[]
    writtenAnswer: string
    isBusy: boolean
    error: string | null
    translation: TranslationViewState
    onToggleTranslation: () => void
    onSelectedChoiceIdsChange: (choiceIds: number[]) => void
    onWrittenAnswerChange: (answer: string) => void
    onNavigate: (questionNumber: number) => void
    onSubmitAnswer: (event: FormEvent<HTMLFormElement>) => void
    onBackToReview: () => void
    onSubmitQuiz: () => void
    onReturnHome: () => void
}

export function StudentQuizPage({
    session,
    question,
    participantToken,
    title,
    contentDirection,
    selectedChoiceIds,
    writtenAnswer,
    isBusy,
    error,
    translation,
    onToggleTranslation,
    onSelectedChoiceIdsChange,
    onWrittenAnswerChange,
    onNavigate,
    onSubmitAnswer,
    onBackToReview,
    onSubmitQuiz,
    onReturnHome,
}: StudentQuizPageProps) {
    const { t } = useTranslation()
    const isReviewing =
        session.awaiting_final_submission && session.status === "in_progress"
    // Correcting an answer leaves the summary; offer the way back to it.
    const canReturnToReview =
        session.allow_answer_review &&
        session.status === "in_progress" &&
        !session.awaiting_final_submission &&
        session.total_questions > 0 &&
        session.answered_count >= session.total_questions

    return (
        <div className="flex w-full max-w-7xl flex-col gap-6 rounded-2xl border bg-secondary px-5 py-6 shadow-lg sm:px-8 sm:py-8 lg:px-12">
            <StudentNameBadge name={session.student_name} />
            <QuizHeader
                session={session}
                title={title}
                contentDirection={contentDirection}
            />
            {translation.offered && (
                <TranslationNotice
                    translation={translation}
                    onToggle={onToggleTranslation}
                />
            )}
            {isReviewing ? (
                <AnswerReview
                    session={session}
                    contentDirection={contentDirection}
                    isBusy={isBusy}
                    error={error}
                    onNavigate={onNavigate}
                    onSubmitQuiz={onSubmitQuiz}
                />
            ) : (
                <>
                    <QuizStatus session={session} onReturnHome={onReturnHome} />
                    {session.status === "in_progress" && question && (
                        <>
                            {canReturnToReview && (
                                <div className="flex justify-center">
                                    <Button
                                        type="button"
                                        variant="outline"
                                        disabled={isBusy}
                                        onClick={onBackToReview}
                                    >
                                        <ListChecks />
                                        {t("back-to-answer-review")}
                                    </Button>
                                </div>
                            )}
                            <StudentQuestionForm
                                session={session}
                                question={question}
                                participantToken={participantToken}
                                contentDirection={contentDirection}
                                selectedChoiceIds={selectedChoiceIds}
                                writtenAnswer={writtenAnswer}
                                isBusy={isBusy}
                                error={error}
                                onSelectedChoiceIdsChange={
                                    onSelectedChoiceIdsChange
                                }
                                onWrittenAnswerChange={onWrittenAnswerChange}
                                onNavigate={onNavigate}
                                onSubmit={onSubmitAnswer}
                            />
                        </>
                    )}
                </>
            )}
        </div>
    )
}

function QuizHeader({
    session,
    title,
    contentDirection,
}: {
    session: StudentQuizSession
    title: string
    contentDirection: "ltr" | "rtl"
}) {
    return (
        <div className="text-center">
            <h1 className="text-3xl font-extrabold" dir={contentDirection}>
                {title}
            </h1>
            <p className="text-muted-foreground">{session.class_name}</p>
            {session.status === "in_progress" && (
                <div className="mt-3">
                    <QuizTimer endsAt={session.ends_at} />
                </div>
            )}
        </div>
    )
}

function QuizStatus({
    session,
    onReturnHome,
}: {
    session: StudentQuizSession
    onReturnHome: () => void
}) {
    const { t } = useTranslation()

    if (session.status === "waiting") {
        return (
            <div className="text-center">
                <LoaderCircle className="mx-auto size-10 animate-spin text-primary motion-reduce:animate-none" />
                <p className="mt-3 font-semibold">
                    {t("student-waiting-for-start")}
                </p>
            </div>
        )
    }

    if (session.status === "paused") {
        return (
            <div className="rounded-xl border border-dashed p-8 text-center">
                <LoaderCircle className="mx-auto size-8 animate-spin text-primary motion-reduce:animate-none" />
                <p className="mt-3 text-xl font-bold">
                    {t("student-quiz-paused")}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                    {t("student-quiz-paused-help")}
                </p>
            </div>
        )
    }

    if (session.status === "cancelled" || session.status === "finished") {
        const cancelled = session.status === "cancelled"
        return (
            <div
                className={
                    cancelled
                        ? "rounded-xl bg-destructive/10 p-6 text-center sm:p-8"
                        : "rounded-xl bg-primary/10 p-6 text-center sm:p-8"
                }
            >
                <p className="text-2xl font-bold">
                    {t(
                        cancelled
                            ? "student-quiz-cancelled"
                            : "student-quiz-finished"
                    )}
                </p>
                <Button
                    className="mx-auto mt-5"
                    size="lg"
                    onClick={onReturnHome}
                >
                    {t("back-home")}
                </Button>
            </div>
        )
    }

    if (session.has_answered && !session.question) {
        return (
            <div className="rounded-xl border border-dashed p-8 text-center">
                <LoaderCircle className="mx-auto size-8 animate-spin text-primary motion-reduce:animate-none" />
                <p className="mt-3 font-semibold">
                    {t("student-answer-recorded")}
                </p>
                <p className="text-sm text-muted-foreground">
                    {t("student-waiting-next")}
                </p>
            </div>
        )
    }

    return null
}

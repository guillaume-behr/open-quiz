import type { StudentQuizQuestion, StudentQuizSession } from "@/api/types"
import { QuizTimer } from "@/components/quizzes/quiz-timer"
import { Button } from "@/components/ui/button"
import { Collapsible as CollapsiblePrimitive } from "@base-ui/react/collapsible"
import {
    ChevronDown,
    Languages,
    LoaderCircle,
    TriangleAlert,
} from "lucide-react"
import type { FormEvent } from "react"
import { useTranslation } from "react-i18next"
import { StudentNameBadge } from "./fullscreen-prompt"
import { StudentQuestionForm } from "./student-question-form"

type TranslationViewState = {
    offered: boolean
    active: boolean
    hasError: boolean
    isTranslating: boolean
    isDownloading: boolean
}

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
    onReturnHome,
}: StudentQuizPageProps) {
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
            <QuizStatus session={session} onReturnHome={onReturnHome} />
            {session.status === "in_progress" && question && (
                <StudentQuestionForm
                    session={session}
                    question={question}
                    participantToken={participantToken}
                    contentDirection={contentDirection}
                    selectedChoiceIds={selectedChoiceIds}
                    writtenAnswer={writtenAnswer}
                    isBusy={isBusy}
                    error={error}
                    onSelectedChoiceIdsChange={onSelectedChoiceIdsChange}
                    onWrittenAnswerChange={onWrittenAnswerChange}
                    onNavigate={onNavigate}
                    onSubmit={onSubmitAnswer}
                />
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

function TranslationNotice({
    translation,
    onToggle,
}: {
    translation: TranslationViewState
    onToggle: () => void
}) {
    const { t } = useTranslation()

    return (
        <CollapsiblePrimitive.Root className="w-full max-w-xl self-center overflow-hidden rounded-xl border border-amber-500/50 bg-amber-500/10">
            <CollapsiblePrimitive.Trigger className="group flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-bold transition-colors select-none hover:bg-amber-500/10 focus-visible:ring-3 focus-visible:ring-amber-500/40 focus-visible:outline-none focus-visible:ring-inset sm:px-4">
                <TriangleAlert
                    className="size-4 shrink-0 text-amber-700 dark:text-amber-300"
                    aria-hidden="true"
                />
                <span>{t("automatic-translation-title")}</span>
                <ChevronDown className="ms-auto size-4 shrink-0 text-amber-800 transition-transform duration-200 ease-out group-data-panel-open:rotate-180 motion-reduce:transition-none dark:text-amber-200" />
            </CollapsiblePrimitive.Trigger>
            <CollapsiblePrimitive.Panel className="h-[var(--collapsible-panel-height)] overflow-hidden opacity-100 transition-[height,opacity] duration-200 ease-out data-ending-style:h-0 data-ending-style:opacity-0 data-starting-style:h-0 data-starting-style:opacity-0 motion-reduce:transition-none [&[hidden]:not([hidden='until-found'])]:hidden">
                <div className="border-t border-amber-500/30 px-3 py-3 sm:px-4">
                    <p className="text-xs leading-5 sm:text-sm">
                        {t("automatic-translation-warning")}
                    </p>
                    {translation.hasError && (
                        <p
                            className="mt-2 text-xs text-destructive sm:text-sm"
                            role="alert"
                        >
                            {t("automatic-translation-unavailable")}
                        </p>
                    )}
                    <Button
                        className="mt-2 h-9"
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={translation.isTranslating}
                        onClick={onToggle}
                    >
                        {translation.isTranslating ? (
                            <LoaderCircle
                                className="animate-spin motion-reduce:animate-none"
                                aria-hidden="true"
                            />
                        ) : (
                            <Languages aria-hidden="true" />
                        )}
                        {translation.isDownloading
                            ? t("automatic-translation-downloading")
                            : translation.isTranslating
                              ? t("automatic-translation-progress")
                              : translation.active
                                ? t("automatic-translation-original")
                                : t("automatic-translation-enable")}
                    </Button>
                </div>
            </CollapsiblePrimitive.Panel>
        </CollapsiblePrimitive.Root>
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

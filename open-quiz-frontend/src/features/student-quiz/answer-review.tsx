import { RichText } from "@/components/ui/rich-text"
import type { StudentQuizSession } from "@/api/types"
import { Button } from "@/components/ui/button"
import { FieldError } from "@/components/ui/field"
import { cn } from "@/lib/utils"
import { CircleCheck, LoaderCircle, Pencil } from "lucide-react"
import { useTranslation } from "react-i18next"

/**
 * Last screen of an exam that allows reviewing answers: nothing is handed in
 * until the student confirms, and the teacher still sees them as working.
 */
export function AnswerReview({
    session,
    contentDirection,
    isBusy,
    error,
    onNavigate,
    onSubmitQuiz,
}: {
    session: StudentQuizSession
    contentDirection: "ltr" | "rtl"
    isBusy: boolean
    error: string | null
    onNavigate: (questionNumber: number) => void
    onSubmitQuiz: () => void
}) {
    const { t } = useTranslation()
    const canEdit = session.allow_previous_questions
    // Skipped questions still unanswered are orange, as in the question
    // navigation: answering one takes the orange away.
    const skipped = new Set(session.skipped_question_numbers)
    const answered = new Set(session.answered_question_numbers)

    return (
        <section className="space-y-5" aria-labelledby="answer-review-title">
            <div className="text-center">
                <h2 id="answer-review-title" className="text-2xl font-bold">
                    {t("answer-review-title")}
                </h2>
                <p className="mt-1 text-muted-foreground">
                    {t(
                        canEdit
                            ? "answer-review-help"
                            : "answer-review-read-help"
                    )}
                </p>
            </div>
            <ol className="space-y-3">
                {session.answer_summaries.map((summary) => {
                    const isSkipped =
                        skipped.has(summary.question_number) &&
                        !answered.has(summary.question_number)
                    return (
                        <li
                            key={summary.question_id}
                            className={cn(
                                "rounded-xl border bg-background p-4",
                                isSkipped &&
                                    "border-orange-300 bg-orange-50 dark:border-orange-400/40 dark:bg-orange-400/10"
                            )}
                        >
                            <div className="flex flex-wrap items-start justify-between gap-3">
                                <div className="min-w-0 flex-1">
                                    <p className="text-sm font-semibold text-primary">
                                        {t("student-question-progress", {
                                            current: summary.question_number,
                                            total: session.total_questions,
                                        })}
                                        {isSkipped && (
                                            <span className="ms-2 inline-flex rounded-md bg-orange-200 px-2 py-0.5 text-xs font-medium text-orange-950 dark:bg-orange-400/30 dark:text-orange-100">
                                                {t(
                                                    "student-question-state-skipped"
                                                )}
                                            </span>
                                        )}
                                    </p>
                                    <p
                                        className="mt-1 font-medium"
                                        dir={contentDirection}
                                    >
                                        <RichText text={summary.prompt} />
                                    </p>
                                </div>
                                {canEdit && (
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        disabled={isBusy}
                                        onClick={() =>
                                            onNavigate(summary.question_number)
                                        }
                                    >
                                        <Pencil />
                                        {t("answer-review-edit")}
                                    </Button>
                                )}
                            </div>
                            <p className="mt-3 text-sm font-semibold">
                                {t("student-answer")}
                            </p>
                            {summary.submitted_answers.length === 0 ? (
                                <p className="text-sm text-muted-foreground">
                                    {t("answer-review-empty")}
                                </p>
                            ) : (
                                <p
                                    className="mt-1 max-h-64 overflow-auto whitespace-pre-wrap"
                                    dir={contentDirection}
                                >
                                    {summary.submitted_answers.join(", ")}
                                </p>
                            )}
                        </li>
                    )
                })}
            </ol>
            {error && <FieldError>{error}</FieldError>}
            <div className="flex flex-col items-center gap-2 border-t pt-5">
                <p className="text-center text-sm text-muted-foreground">
                    {t("answer-review-final-warning")}
                </p>
                <Button
                    className="sm:min-w-72"
                    type="button"
                    size="lg"
                    disabled={isBusy}
                    onClick={onSubmitQuiz}
                >
                    {isBusy ? (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    ) : (
                        <CircleCheck />
                    )}
                    {t("submit-quiz-final")}
                </Button>
            </div>
        </section>
    )
}

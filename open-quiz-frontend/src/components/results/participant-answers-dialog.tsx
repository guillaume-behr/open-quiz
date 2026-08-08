import type { QuizAnswerReview, QuizParticipant } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { LoaderCircle, Save } from "lucide-react"
import { useTranslation } from "react-i18next"

type ParticipantAnswersDialogProps = {
    participant: QuizParticipant | null
    answers: QuizAnswerReview[]
    isLoading: boolean
    hasError: boolean
    scoreDrafts: Record<number, string>
    gradingAnswerId: number | null
    locale: string
    onClose: () => void
    onScoreDraftChange: (answerId: number, score: string) => void
    onGrade: (answer: QuizAnswerReview) => void
}

function formatScore(score: number, locale: string) {
    return new Intl.NumberFormat(locale, {
        maximumFractionDigits: 2,
    }).format(score)
}

export function ParticipantAnswersDialog({
    participant,
    answers,
    isLoading,
    hasError,
    scoreDrafts,
    gradingAnswerId,
    locale,
    onClose,
    onScoreDraftChange,
    onGrade,
}: ParticipantAnswersDialogProps) {
    const { t } = useTranslation()

    return (
        <Dialog
            open={participant !== null}
            onOpenChange={(open) => {
                if (!open && gradingAnswerId === null) onClose()
            }}
            title={t("student-answers")}
            description={
                participant?.student_display_name ??
                participant?.student_identifier
            }
            className="max-w-3xl"
        >
            {isLoading ? (
                <div className="flex min-h-40 items-center justify-center">
                    <LoaderCircle className="size-7 animate-spin text-primary motion-reduce:animate-none" />
                </div>
            ) : (
                <div className="space-y-3">
                    {hasError && (
                        <p className="text-sm text-destructive" role="alert">
                            {t("answers-load-error")}
                        </p>
                    )}
                    {answers.map((answer) => (
                        <AnswerReview
                            key={answer.id}
                            answer={answer}
                            scoreDraft={scoreDrafts[answer.id] ?? ""}
                            isGrading={gradingAnswerId === answer.id}
                            locale={locale}
                            onScoreDraftChange={(score) =>
                                onScoreDraftChange(answer.id, score)
                            }
                            onGrade={() => onGrade(answer)}
                        />
                    ))}
                </div>
            )}
        </Dialog>
    )
}

function AnswerReview({
    answer,
    scoreDraft,
    isGrading,
    locale,
    onScoreDraftChange,
    onGrade,
}: {
    answer: QuizAnswerReview
    scoreDraft: string
    isGrading: boolean
    locale: string
    onScoreDraftChange: (score: string) => void
    onGrade: () => void
}) {
    const { t } = useTranslation()
    return (
        <article className="rounded-xl border p-4">
            <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                <div className="min-w-0">
                    <p className="text-xs font-semibold text-muted-foreground">
                        {t("question-number", { number: answer.position })} ·{" "}
                        {t(`difficulty-${answer.difficulty}`)}
                    </p>
                    <h3 className="mt-1 font-semibold">{answer.prompt}</h3>
                </div>
                <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium whitespace-nowrap tabular-nums">
                    {formatScore(answer.score, locale)} /{" "}
                    {formatScore(answer.max_score, locale)} {t("points-short")}
                </span>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <AnswerText
                    label={t("student-answer")}
                    value={
                        answer.submitted_answers.join(", ") || t("no-answer")
                    }
                    correctness={answer.is_correct}
                />
                <AnswerText
                    label={t("expected-answer-help")}
                    value={answer.expected_answers.join(", ")}
                    highlighted
                />
            </div>
            {answer.answer_mode === "written" && (
                <div className="mt-3 flex flex-wrap items-end gap-2 border-t pt-3">
                    <label className="text-sm font-medium">
                        {t("manual-score")}
                        <span className="mt-1 flex items-center gap-2">
                            <Input
                                className="w-28"
                                type="number"
                                min={0}
                                max={answer.max_score}
                                step="0.25"
                                value={scoreDraft}
                                onChange={(event) =>
                                    onScoreDraftChange(event.target.value)
                                }
                            />
                            <span className="whitespace-nowrap text-muted-foreground tabular-nums">
                                / {formatScore(answer.max_score, locale)}{" "}
                                {t("points-short")}
                            </span>
                        </span>
                    </label>
                    <Button
                        type="button"
                        size="sm"
                        disabled={isGrading}
                        onClick={onGrade}
                    >
                        {isGrading ? (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        ) : (
                            <Save />
                        )}
                        {t(answer.is_graded ? "update-grade" : "grade-answer")}
                    </Button>
                </div>
            )}
        </article>
    )
}

function AnswerText({
    label,
    value,
    highlighted = false,
    correctness,
}: {
    label: string
    value: string
    highlighted?: boolean
    correctness?: boolean | null
}) {
    const { t } = useTranslation()
    return (
        <div
            className={
                highlighted
                    ? "rounded-lg bg-primary/5 p-3"
                    : correctness === true
                      ? "rounded-lg border border-emerald-500/40 bg-emerald-500/10 p-3 text-emerald-800 dark:text-emerald-200"
                      : correctness === false
                        ? "rounded-lg border border-destructive/40 bg-destructive/10 p-3 text-destructive"
                        : "rounded-lg bg-muted/60 p-3"
            }
        >
            <p className="text-xs font-medium">
                {label}
                {correctness !== undefined && correctness !== null && (
                    <span className="sr-only">
                        {` — ${t(correctness ? "training-correct" : "training-incorrect")}`}
                    </span>
                )}
            </p>
            <p className="mt-1 text-sm whitespace-pre-wrap">{value}</p>
        </div>
    )
}

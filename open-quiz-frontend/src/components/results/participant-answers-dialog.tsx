import { RichText } from "@/components/ui/rich-text"
import type { QuizAnswerReview, QuizParticipant } from "@/api/types"
import { answerOutcomeKey, formatScore } from "@/lib/grades"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { StaticCodeBlock } from "@/components/question-banks/code-block"
import { scoreGradientStyle } from "@/lib/utils"
import { SubmittedAnswer } from "@/components/shared/submitted-answer"
import { LoaderCircle, Save } from "lucide-react"
import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { LoadingState } from "@/components/ui/loading-state"

type ParticipantAnswersDialogProps = {
    participant: QuizParticipant | null
    answers: QuizAnswerReview[]
    isLoading: boolean
    error: string | null
    scoreDrafts: Record<number, string>
    feedbackDrafts: Record<number, string>
    gradingAnswerId: number | null
    isReadOnly: boolean
    locale: string
    onClose: () => void
    onScoreDraftChange: (answerId: number, score: string) => void
    onFeedbackDraftChange: (answerId: number, feedback: string) => void
    onGrade: (answer: QuizAnswerReview) => void
}

export function ParticipantAnswersDialog({
    participant,
    answers,
    isLoading,
    error,
    scoreDrafts,
    feedbackDrafts,
    gradingAnswerId,
    isReadOnly,
    locale,
    onClose,
    onScoreDraftChange,
    onFeedbackDraftChange,
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
            size="xl"
        >
            {isLoading ? (
                <LoadingState />
            ) : (
                <div className="space-y-3">
                    {error && (
                        <p className="text-sm text-destructive" role="alert">
                            {error}
                        </p>
                    )}
                    {answers.map((answer) => (
                        <AnswerReview
                            key={answer.id}
                            answer={answer}
                            scoreDraft={scoreDrafts[answer.id] ?? ""}
                            feedbackDraft={feedbackDrafts[answer.id] ?? ""}
                            isGrading={gradingAnswerId === answer.id}
                            isReadOnly={isReadOnly}
                            locale={locale}
                            onScoreDraftChange={(score) =>
                                onScoreDraftChange(answer.id, score)
                            }
                            onFeedbackDraftChange={(feedback) =>
                                onFeedbackDraftChange(answer.id, feedback)
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
    feedbackDraft,
    isGrading,
    isReadOnly,
    locale,
    onScoreDraftChange,
    onFeedbackDraftChange,
    onGrade,
}: {
    answer: QuizAnswerReview
    scoreDraft: string
    feedbackDraft: string
    isGrading: boolean
    isReadOnly: boolean
    locale: string
    onScoreDraftChange: (score: string) => void
    onFeedbackDraftChange: (feedback: string) => void
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
                    <h3 className="mt-1 font-medium">
                        <RichText text={answer.prompt} />
                    </h3>
                    {answer.code_content && answer.code_language && (
                        <div className="mt-3">
                            <StaticCodeBlock
                                code={answer.code_content}
                                language={answer.code_language}
                            />
                        </div>
                    )}
                </div>
                <span className="rounded-full bg-muted px-2.5 py-1 text-xs font-medium whitespace-nowrap tabular-nums">
                    {formatScore(answer.score, locale)} /{" "}
                    {formatScore(answer.max_score, locale)} {t("points-short")}
                </span>
            </div>
            <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <AnswerText
                    label={t("student-answer")}
                    graded={answer.is_correct !== null}
                    score={answer.score}
                    maxScore={answer.max_score}
                >
                    <SubmittedAnswer
                        values={answer.submitted_answers}
                        language={answer.response_language}
                        placeholder={t("no-answer")}
                    />
                </AnswerText>
                <AnswerText label={t("expected-answer-help")} highlighted>
                    <SubmittedAnswer
                        values={answer.expected_answers}
                        language={answer.response_language}
                        placeholder="—"
                    />
                </AnswerText>
            </div>
            {answer.answer_mode === "written" && (
                <div className="mt-3 space-y-3 border-t pt-3">
                    <label className="block text-sm font-medium">
                        {t("teacher-feedback")}
                        <textarea
                            className="mt-1 block w-full rounded-md border bg-background px-3 py-2 text-sm shadow-xs placeholder:text-muted-foreground focus-visible:ring-1 focus-visible:ring-ring focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                            rows={2}
                            placeholder={t("teacher-feedback-placeholder")}
                            value={feedbackDraft}
                            disabled={isReadOnly}
                            onChange={(event) =>
                                onFeedbackDraftChange(event.target.value)
                            }
                        />
                    </label>
                    <div className="flex flex-wrap items-end gap-2">
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
                                    disabled={isReadOnly}
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
                            disabled={isGrading || isReadOnly}
                            onClick={onGrade}
                        >
                            {isGrading ? (
                                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                            ) : (
                                <Save />
                            )}
                            {t(
                                answer.is_graded
                                    ? "update-grade"
                                    : "grade-answer"
                            )}
                        </Button>
                    </div>
                </div>
            )}
            {answer.answer_mode !== "written" && answer.feedback && (
                <div className="mt-3 rounded-lg border border-primary/20 bg-primary/5 p-3 text-sm">
                    <p className="font-semibold text-primary">
                        {t("teacher-feedback")}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap text-foreground">
                        {answer.feedback}
                    </p>
                </div>
            )}
        </article>
    )
}

function AnswerText({
    label,
    highlighted = false,
    graded = false,
    score,
    maxScore,
    children,
}: {
    label: string
    highlighted?: boolean
    graded?: boolean
    score?: number
    maxScore?: number
    children: ReactNode
}) {
    const { t } = useTranslation()
    const style =
        graded && score !== undefined && maxScore !== undefined
            ? scoreGradientStyle(score, maxScore)
            : undefined

    return (
        <div
            className={
                highlighted
                    ? "rounded-lg bg-primary/5 p-3"
                    : style
                      ? "rounded-lg border p-3"
                      : "rounded-lg bg-muted/60 p-3"
            }
            style={style}
        >
            <p className="text-xs font-medium">
                {label}
                {style && score !== undefined && maxScore !== undefined && (
                    <span className="sr-only">
                        {` — ${t(answerOutcomeKey(score, maxScore))}`}
                    </span>
                )}
            </p>
            {children}
        </div>
    )
}

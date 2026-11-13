import { RichText } from "@/components/ui/rich-text"
import { getStudentQuizHistory } from "@/api/student-auth"
import type { StudentQuizHistoryItem } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Grade } from "@/components/ui/grade"
import { StaticCodeBlock } from "@/components/question-banks/code-block"
import { SubmittedAnswer } from "@/components/submitted-answer"
import { formatScore, scoreTone, type ScoreTone } from "@/lib/grades"
import { cn, scoreGradientStyle } from "@/lib/utils"
import { Accordion } from "@base-ui/react/accordion"
import { BookOpenCheck, ChevronDown, TriangleAlert } from "lucide-react"
import { useCallback, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { useLocale } from "@/lib/locale"
import { useResource } from "@/hooks/use-resource"
import { LoadingState } from "@/components/ui/loading-state"

const SCORE_TONE_CLASS_NAMES: Record<ScoreTone, string> = {
    success: "bg-success/10 text-success",
    warning: "bg-warning/10 text-warning",
    destructive: "bg-destructive/10 text-destructive",
}

/** One question's points out of its maximum, colored by how much it earned.
 * An answer still waiting for the teacher's grading shows no score yet. */
function QuestionScorePill({
    score,
    maxScore,
    graded,
    locale,
}: {
    score: number
    maxScore: number
    graded: boolean
    locale: string
}) {
    const { t } = useTranslation()
    return (
        <span
            className={cn(
                "rounded-full px-2.5 py-1 text-xs font-semibold whitespace-nowrap tabular-nums",
                graded
                    ? SCORE_TONE_CLASS_NAMES[scoreTone(score, maxScore)]
                    : "bg-muted text-muted-foreground"
            )}
        >
            {graded ? formatScore(score, locale) : "–"} /{" "}
            {formatScore(maxScore, locale)} {t("points-short")}
        </span>
    )
}

export function StudentQuizHistory({ token }: { token: string }) {
    const { t } = useTranslation()
    const locale = useLocale()
    // Reloads, and drops a stale answer, when the token changes.
    const history = useResource(
        useCallback(() => getStudentQuizHistory(token), [token])
    )
    const items = history.data ?? []
    const isLoading = history.isLoading
    const hasError = Boolean(history.error)
    const [provisionalNoticeItem, setProvisionalNoticeItem] =
        useState<StudentQuizHistoryItem | null>(null)
    const openSessionIdsRef = useRef<number[]>([])
    const dateFormatter = useMemo(
        () =>
            new Intl.DateTimeFormat(locale, {
                dateStyle: "long",
            }),
        [locale]
    )

    function handleAccordionValueChange(sessionIds: number[]) {
        const newlyOpenedIds = sessionIds.filter(
            (id) => !openSessionIdsRef.current.includes(id)
        )
        openSessionIdsRef.current = sessionIds
        const newlyOpenedProvisionalItem = items.find(
            (item) =>
                newlyOpenedIds.includes(item.session_id) &&
                !item.grades_published &&
                item.correction_available
        )
        if (newlyOpenedProvisionalItem) {
            setProvisionalNoticeItem(newlyOpenedProvisionalItem)
        }
    }

    if (isLoading) return <LoadingState className="py-10" />

    if (hasError)
        return (
            <p className="py-8 text-center text-destructive" role="alert">
                {t("quiz-history-error")}
            </p>
        )

    if (!items.length)
        return (
            <div className="py-8 text-center text-muted-foreground">
                <BookOpenCheck className="mx-auto mb-3 size-9" />
                <p className="font-medium">{t("quiz-history-empty")}</p>
                <p className="mt-1 text-sm">{t("quiz-history-empty-help")}</p>
            </div>
        )

    return (
        <>
            <Accordion.Root
                multiple
                key={items.map((item) => item.session_id).join(",")}
                onValueChange={handleAccordionValueChange}
                className="grid animate-in gap-3 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none"
            >
                {items.map((item) => (
                    <Accordion.Item
                        key={item.session_id}
                        value={item.session_id}
                        className="overflow-hidden rounded-xl border bg-background"
                    >
                        <Accordion.Header>
                            <Accordion.Trigger className="group flex w-full items-center justify-between gap-3 rounded-xl p-4 text-start transition-colors hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none">
                                <span>
                                    <span className="block font-semibold">
                                        {item.quiz_title}
                                    </span>
                                    <span className="mt-1 block text-xs text-muted-foreground">
                                        {dateFormatter.format(
                                            new Date(item.started_at)
                                        )}
                                    </span>
                                    {!item.correction_available && (
                                        <span className="mt-2 inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
                                            <TriangleAlert className="size-3" />
                                            {t("grades-not-published")}
                                        </span>
                                    )}
                                    {item.score !== null &&
                                        item.maximum_score !== null && (
                                            <span className="mt-2 flex flex-wrap items-center gap-2">
                                                <Grade
                                                    className="font-bold text-primary"
                                                    score={item.score}
                                                    maximumScore={
                                                        item.maximum_score
                                                    }
                                                    format={(grade, scale) =>
                                                        t("published-grade", {
                                                            grade,
                                                            scale,
                                                        })
                                                    }
                                                    // The grade sits inside
                                                    // the accordion trigger.
                                                    focusable={false}
                                                />
                                                {!item.grades_published && (
                                                    <span className="inline-flex items-center gap-1 rounded-full bg-warning/10 px-2 py-0.5 text-xs font-medium text-warning">
                                                        <TriangleAlert className="size-3" />
                                                        {t(
                                                            "grades-not-published"
                                                        )}
                                                    </span>
                                                )}
                                            </span>
                                        )}
                                </span>
                                <span className="flex shrink-0 items-center gap-2 text-sm font-medium text-primary">
                                    {t(
                                        item.correction_available
                                            ? "view-correction"
                                            : "view-my-answers"
                                    )}
                                    <ChevronDown className="size-4 transition-transform duration-200 ease-out group-data-panel-open:rotate-180 motion-reduce:transition-none" />
                                </span>
                            </Accordion.Trigger>
                        </Accordion.Header>
                        <Accordion.Panel className="h-[var(--accordion-panel-height)] overflow-hidden opacity-100 transition-[height,opacity] duration-200 ease-out data-ending-style:h-0 data-ending-style:opacity-0 data-starting-style:h-0 data-starting-style:opacity-0 motion-reduce:transition-none">
                            <div className="grid gap-3 border-t p-4">
                                {!item.correction_available && (
                                    <p className="text-sm text-muted-foreground">
                                        {t("quiz-history-correction-pending")}
                                    </p>
                                )}
                                {item.answers.map((answer) => (
                                    <article
                                        key={answer.question_id}
                                        className="rounded-lg border p-3"
                                    >
                                        <div className="grid grid-cols-[minmax(0,1fr)_auto] items-start gap-3">
                                            <div className="min-w-0">
                                                <p className="text-xs font-semibold text-muted-foreground">
                                                    {t("question-number", {
                                                        number: answer.position,
                                                    })}
                                                </p>
                                                <h3 className="mt-1 font-medium">
                                                    <RichText
                                                        text={answer.prompt}
                                                    />
                                                </h3>
                                            </div>
                                            {answer.score !== null && (
                                                <QuestionScorePill
                                                    score={answer.score}
                                                    maxScore={answer.max_score}
                                                    graded={
                                                        answer.is_correct !==
                                                        null
                                                    }
                                                    locale={locale}
                                                />
                                            )}
                                        </div>
                                        {answer.code_content &&
                                            answer.code_language && (
                                                <div className="mt-2">
                                                    <StaticCodeBlock
                                                        code={
                                                            answer.code_content
                                                        }
                                                        language={
                                                            answer.code_language
                                                        }
                                                    />
                                                </div>
                                            )}
                                        <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                                            <div
                                                className={
                                                    answer.is_correct === null
                                                        ? "rounded-lg border bg-muted/30 p-3"
                                                        : "rounded-lg border p-3"
                                                }
                                                style={
                                                    answer.is_correct ===
                                                        null ||
                                                    answer.score === null
                                                        ? undefined
                                                        : scoreGradientStyle(
                                                              answer.score,
                                                              answer.max_score
                                                          )
                                                }
                                            >
                                                <p
                                                    className={
                                                        answer.is_correct ===
                                                        null
                                                            ? "font-medium text-muted-foreground"
                                                            : "font-medium"
                                                    }
                                                >
                                                    {t("student-answer")}
                                                    {answer.is_correct ===
                                                        false && (
                                                        <span className="sr-only">
                                                            {` — ${t("training-incorrect")}`}
                                                        </span>
                                                    )}
                                                </p>
                                                <SubmittedAnswer
                                                    values={
                                                        answer.submitted_answers
                                                    }
                                                    language={
                                                        answer.response_language
                                                    }
                                                    placeholder={t("no-answer")}
                                                />
                                                {item.correction_available &&
                                                    answer.is_correct ===
                                                        null && (
                                                        <p className="mt-2 text-xs font-medium text-muted-foreground">
                                                            {t(
                                                                "training-manual-review"
                                                            )}
                                                        </p>
                                                    )}
                                            </div>
                                            {item.correction_available && (
                                                <div className="rounded-lg bg-success/10 p-3">
                                                    <p className="font-medium text-success">
                                                        {t("correct-answer")}
                                                    </p>
                                                    <SubmittedAnswer
                                                        values={
                                                            answer.expected_answers
                                                        }
                                                        language={
                                                            answer.response_language
                                                        }
                                                        placeholder="—"
                                                    />
                                                </div>
                                            )}
                                        </div>
                                        {answer.feedback && (
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
                                ))}
                            </div>
                        </Accordion.Panel>
                    </Accordion.Item>
                ))}
            </Accordion.Root>
            <Dialog
                open={provisionalNoticeItem !== null}
                onOpenChange={(open) => !open && setProvisionalNoticeItem(null)}
                title={t("provisional-grades-title")}
                description={provisionalNoticeItem?.quiz_title}
                size="sm"
            >
                <p className="text-sm text-muted-foreground">
                    {t("provisional-grades-body")}
                </p>
                <div className="mt-5 flex justify-end">
                    <Button onClick={() => setProvisionalNoticeItem(null)}>
                        {t("close")}
                    </Button>
                </div>
            </Dialog>
        </>
    )
}

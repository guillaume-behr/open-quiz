import { getStudentQuizHistory } from "@/api/student-auth"
import type { StudentQuizHistoryItem } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { scoreGradientStyle } from "@/lib/utils"
import { Accordion } from "@base-ui/react/accordion"
import {
    BookOpenCheck,
    ChevronDown,
    LoaderCircle,
    TriangleAlert,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

export function StudentQuizHistory({ token }: { token: string }) {
    const { t, i18n } = useTranslation()
    const [items, setItems] = useState<StudentQuizHistoryItem[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [hasError, setHasError] = useState(false)
    const [provisionalNoticeItem, setProvisionalNoticeItem] =
        useState<StudentQuizHistoryItem | null>(null)
    const openSessionIdsRef = useRef<number[]>([])
    const dateFormatter = useMemo(
        () =>
            new Intl.DateTimeFormat(i18n.language, {
                dateStyle: "long",
            }),
        [i18n.language]
    )

    useEffect(() => {
        getStudentQuizHistory(token)
            .then(setItems)
            .catch(() => setHasError(true))
            .finally(() => setIsLoading(false))
    }, [token])

    function handleAccordionValueChange(sessionIds: number[]) {
        const newlyOpenedIds = sessionIds.filter(
            (id) => !openSessionIdsRef.current.includes(id)
        )
        openSessionIdsRef.current = sessionIds
        const newlyOpenedProvisionalItem = items.find(
            (item) =>
                newlyOpenedIds.includes(item.session_id) &&
                !item.grades_published
        )
        if (newlyOpenedProvisionalItem) {
            setProvisionalNoticeItem(newlyOpenedProvisionalItem)
        }
    }

    if (isLoading)
        return (
            <div
                className="flex justify-center py-10"
                role="status"
                aria-label={t("page-loading")}
            >
                <LoaderCircle
                    className="size-7 animate-spin text-primary motion-reduce:animate-none"
                    aria-hidden="true"
                />
            </div>
        )

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
                                    {item.score !== null &&
                                        item.maximum_score !== null && (
                                            <span className="mt-2 flex flex-wrap items-center gap-2">
                                                <span className="font-bold text-primary">
                                                    {t("published-grade", {
                                                        score: item.score,
                                                        maximum:
                                                            item.maximum_score,
                                                    })}
                                                </span>
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
                                    {t("view-correction")}
                                    <ChevronDown className="size-4 transition-transform duration-200 ease-out group-data-panel-open:rotate-180 motion-reduce:transition-none" />
                                </span>
                            </Accordion.Trigger>
                        </Accordion.Header>
                        <Accordion.Panel className="h-[var(--accordion-panel-height)] overflow-hidden opacity-100 transition-[height,opacity] duration-200 ease-out data-ending-style:h-0 data-ending-style:opacity-0 data-starting-style:h-0 data-starting-style:opacity-0 motion-reduce:transition-none">
                            <div className="grid gap-3 border-t p-4">
                                {item.answers.map((answer) => (
                                    <article
                                        key={answer.question_id}
                                        className="rounded-lg border p-3"
                                    >
                                        <p className="text-xs font-semibold text-muted-foreground">
                                            {t("question-number", {
                                                number: answer.position,
                                            })}
                                        </p>
                                        <h3 className="mt-1 font-semibold">
                                            {answer.prompt}
                                        </h3>
                                        <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                                            <div
                                                className={
                                                    answer.is_correct === null
                                                        ? "rounded-lg border bg-muted/30 p-3"
                                                        : "rounded-lg border p-3"
                                                }
                                                style={
                                                    answer.is_correct === null
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
                                                <p className="mt-1 whitespace-pre-wrap">
                                                    {answer.submitted_answers.join(
                                                        ", "
                                                    ) || t("no-answer")}
                                                </p>
                                                {answer.is_correct === null && (
                                                    <p className="mt-2 text-xs font-medium text-muted-foreground">
                                                        {t(
                                                            "training-manual-review"
                                                        )}
                                                    </p>
                                                )}
                                            </div>
                                            <div className="rounded-lg bg-success/10 p-3">
                                                <p className="font-medium text-success">
                                                    {t("correct-answer")}
                                                </p>
                                                <p className="mt-1 whitespace-pre-wrap">
                                                    {answer.expected_answers.join(
                                                        ", "
                                                    ) || "—"}
                                                </p>
                                            </div>
                                        </div>
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

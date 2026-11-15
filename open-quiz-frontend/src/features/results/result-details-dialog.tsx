import type { QuizParticipant, QuizSession } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Grade } from "@/components/ui/grade"
import { formatScore } from "@/lib/grades"
import { cn } from "@/lib/utils"
import { Tooltip } from "@base-ui/react/tooltip"
import { FileText, LoaderCircle, TriangleAlert, UserRound } from "lucide-react"
import { useTranslation } from "react-i18next"

function ResultIndicator({ label }: { label: string }) {
    return (
        <Tooltip.Root>
            <Tooltip.Trigger
                aria-label={label}
                className="inline-flex size-7 shrink-0 items-center justify-center rounded-full text-warning transition-colors hover:bg-warning/10 focus-visible:ring-2 focus-visible:ring-warning/50 focus-visible:outline-none"
            >
                <TriangleAlert className="size-4" aria-hidden="true" />
            </Tooltip.Trigger>
            <Tooltip.Portal>
                <Tooltip.Positioner sideOffset={8} className="z-60">
                    <Tooltip.Popup
                        role="tooltip"
                        className="max-w-64 rounded-lg border bg-popover px-3 py-2 text-xs font-medium text-popover-foreground shadow-md transition-[transform,opacity] duration-100 data-ending-style:scale-95 data-ending-style:opacity-0 data-starting-style:scale-95 data-starting-style:opacity-0 motion-reduce:transition-none"
                    >
                        {label}
                    </Tooltip.Popup>
                </Tooltip.Positioner>
            </Tooltip.Portal>
        </Tooltip.Root>
    )
}

/**
 * One finished exam: its publication state, its figures and each
 * participant's score, with a way into their answers.
 */
export function ResultDetailsDialog({
    result,
    description,
    locale,
    isPublishing,
    publishError,
    onPublish,
    onOpenParticipant,
    onClose,
}: {
    result: QuizSession | null
    description: string | undefined
    locale: string
    isPublishing: boolean
    publishError: string | null
    onPublish: () => void
    onOpenParticipant: (participant: QuizParticipant) => void
    onClose: () => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={result !== null}
            onOpenChange={(open) => {
                if (!open) onClose()
            }}
            title={result?.quiz_title ?? t("results")}
            description={description}
            size="xl"
        >
            {result && (
                <div className="space-y-4">
                    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-muted/40 p-4">
                        <div>
                            <p className="font-semibold">
                                {t(
                                    result.grades_published_at
                                        ? "grades-published"
                                        : "grades-not-published"
                                )}
                            </p>
                            <p className="text-sm text-muted-foreground">
                                {t("publish-grades-help")}
                            </p>
                        </div>
                        <Button
                            type="button"
                            disabled={
                                result.grades_published_at !== null ||
                                result.participants.some(
                                    (participant) =>
                                        participant.pending_manual_grading_count >
                                        0
                                ) ||
                                isPublishing
                            }
                            onClick={onPublish}
                        >
                            {isPublishing && (
                                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                            )}
                            {t(
                                result.grades_published_at
                                    ? "grades-published"
                                    : "publish-grades"
                            )}
                        </Button>
                        {publishError && (
                            <p
                                className="w-full text-sm text-destructive"
                                role="alert"
                            >
                                {publishError}
                            </p>
                        )}
                    </div>
                    <div className="grid gap-3 sm:grid-cols-3">
                        <div className="rounded-xl bg-muted p-4">
                            <p className="text-xs font-medium text-muted-foreground">
                                {t("result-participants")}
                            </p>
                            <p className="mt-1 font-semibold">
                                {result.participant_count}
                            </p>
                        </div>
                        <div className="rounded-xl bg-muted p-4">
                            <p className="text-xs font-medium text-muted-foreground">
                                {t("result-median-maximum")}
                            </p>
                            <p className="mt-1 font-semibold">
                                {formatScore(
                                    result.median_maximum_score,
                                    locale
                                )}{" "}
                                {t("points-short")}
                            </p>
                        </div>
                        <div className="rounded-xl bg-muted p-4">
                            <p className="text-xs font-medium text-muted-foreground">
                                {t("quiz-question-count")}
                            </p>
                            <p className="mt-1 font-semibold">
                                {result.total_questions}
                            </p>
                        </div>
                    </div>

                    <div className="overflow-hidden rounded-xl border">
                        <div className="hidden grid-cols-[minmax(180px,1fr)_140px_180px_140px] items-center gap-4 border-b bg-muted/60 px-4 py-3 text-xs font-semibold text-muted-foreground md:grid">
                            <span>{t("student-name")}</span>
                            <span>{t("result-progress")}</span>
                            <span className="text-end">
                                {t("result-score-total")}
                            </span>
                            <span>{t("answers")}</span>
                        </div>
                        <Tooltip.Provider delay={250}>
                            <div className="divide-y">
                                {result.participants.map((participant) => (
                                    <div
                                        key={participant.id}
                                        data-participant-id={participant.id}
                                        className={cn(
                                            "grid gap-3 px-4 py-4 md:grid-cols-[minmax(180px,1fr)_140px_180px_140px] md:items-center md:gap-4",
                                            participant.pending_manual_grading_count >
                                                0 && "bg-warning/10"
                                        )}
                                    >
                                        <div className="flex min-w-0 items-center gap-3">
                                            <div
                                                data-grading-status={
                                                    participant.pending_manual_grading_count >
                                                    0
                                                        ? "pending"
                                                        : "complete"
                                                }
                                                className={cn(
                                                    "rounded-full p-2",
                                                    participant.pending_manual_grading_count >
                                                        0
                                                        ? "bg-warning/10 text-warning"
                                                        : "bg-success/10 text-success"
                                                )}
                                            >
                                                <UserRound className="size-4" />
                                            </div>
                                            <div className="min-w-0">
                                                <p className="flex items-center gap-1 font-semibold">
                                                    <span className="truncate">
                                                        {participant.student_display_name ??
                                                            participant.student_identifier}
                                                    </span>
                                                    {participant.pending_manual_grading_count >
                                                        0 && (
                                                        <ResultIndicator
                                                            label={t(
                                                                "answers-pending-grading",
                                                                {
                                                                    count: participant.pending_manual_grading_count,
                                                                }
                                                            )}
                                                        />
                                                    )}
                                                    {Math.abs(
                                                        participant.maximum_score -
                                                            result.median_maximum_score
                                                    ) >= 3 && (
                                                        <ResultIndicator
                                                            label={t(
                                                                "result-maximum-median-gap",
                                                                {
                                                                    maximum:
                                                                        formatScore(
                                                                            participant.maximum_score,
                                                                            locale
                                                                        ),
                                                                    median: formatScore(
                                                                        result.median_maximum_score,
                                                                        locale
                                                                    ),
                                                                }
                                                            )}
                                                        />
                                                    )}
                                                </p>
                                                {participant.student_display_name &&
                                                    participant.student_display_name !==
                                                        participant.student_identifier && (
                                                        <p className="truncate text-xs text-muted-foreground">
                                                            {
                                                                participant.student_identifier
                                                            }
                                                        </p>
                                                    )}
                                            </div>
                                        </div>
                                        <p className="text-sm">
                                            <span className="md:hidden">
                                                {t("result-progress")} :{" "}
                                            </span>
                                            {participant.answered_count} /{" "}
                                            {result.total_questions}
                                            {participant.skipped_count > 0 && (
                                                <span className="ms-2 inline-flex rounded-md bg-orange-200 px-2 py-0.5 text-xs font-medium text-orange-950 dark:bg-orange-400/30 dark:text-orange-100">
                                                    {t(
                                                        "teacher-student-skipped",
                                                        {
                                                            count: participant.skipped_count,
                                                        }
                                                    )}
                                                </span>
                                            )}
                                        </p>
                                        <div
                                            data-participant-score
                                            className="flex items-center justify-between gap-2 text-end font-bold text-primary tabular-nums md:justify-end md:whitespace-nowrap"
                                        >
                                            <span className="font-normal text-foreground md:hidden">
                                                {t("result-score-total")} :{" "}
                                            </span>
                                            <span className="inline-flex items-center justify-end gap-1">
                                                <Grade
                                                    score={participant.score}
                                                    maximumScore={
                                                        participant.maximum_score
                                                    }
                                                />
                                            </span>
                                        </div>
                                        <div className="flex items-center gap-2">
                                            <Button
                                                type="button"
                                                size="sm"
                                                variant="outline"
                                                onClick={() =>
                                                    onOpenParticipant(
                                                        participant
                                                    )
                                                }
                                            >
                                                <FileText />
                                                {t("view-answers")}
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                                {result.participants.length === 0 && (
                                    <p className="p-6 text-center text-sm text-muted-foreground">
                                        {t("result-no-participants")}
                                    </p>
                                )}
                            </div>
                        </Tooltip.Provider>
                    </div>
                </div>
            )}
        </Dialog>
    )
}

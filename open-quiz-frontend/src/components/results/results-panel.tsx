import {
    deleteQuizSession,
    getParticipantAnswers,
    getQuizResults,
    gradeWrittenAnswer,
    publishQuizGrades,
} from "@/api/quizzes"
import { getAllStudentClasses } from "@/api/classes"
import type {
    QuizAnswerReview,
    QuizParticipant,
    QuizSession,
} from "@/api/types"
import { ParticipantAnswersDialog } from "@/components/results/participant-answers-dialog"
import { ResultsExportDialog } from "@/components/results/results-export-dialog"
import { ResultsSchedule } from "@/components/results/results-schedule"
import { resultStart } from "@/components/results/results-utils"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Grade } from "@/components/ui/grade"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { Pagination } from "@/components/ui/pagination"
import { formatScore } from "@/lib/grades"
import { cn, formatClassName } from "@/lib/utils"
import { Tooltip } from "@base-ui/react/tooltip"
import {
    CalendarDays,
    CalendarRange,
    ChartColumn,
    CheckCircle2,
    Eye,
    FileText,
    LoaderCircle,
    LayoutGrid,
    School,
    Trash2,
    TriangleAlert,
    UserRound,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { apiErrorMessage } from "@/lib/errors"
import { useAsyncAction } from "@/hooks/use-async-action"
import { useResource } from "@/hooks/use-resource"

type ResultsViewMode = "cards" | "schedule"

const RESULTS_VIEW_STORAGE_KEY = "open-quiz-teacher-results-view"

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

function storedResultsView(): ResultsViewMode {
    try {
        const stored = localStorage.getItem(RESULTS_VIEW_STORAGE_KEY)
        return stored === "schedule" ? "schedule" : "cards"
    } catch {
        return "cards"
    }
}

function roundScore(score: number): number {
    return Math.round((score + Number.EPSILON) * 100) / 100
}

type ResultsPanelProps = {
    isExportDialogOpen: boolean
    onExportDialogOpenChange: (open: boolean) => void
}

export function ResultsPanel({
    isExportDialogOpen,
    onExportDialogOpenChange,
}: ResultsPanelProps) {
    const { t, i18n } = useTranslation()
    const [page, setPage] = useState(1)
    const [quizFilter, setQuizFilter] = useState("")
    const [classFilter, setClassFilter] = useState("")
    const resultList = useResource(
        useCallback(
            () => getQuizResults(page, quizFilter.trim(), classFilter.trim()),
            [classFilter, page, quizFilter]
        )
    )
    const results = resultList.data?.items ?? []
    const totalPages = resultList.data?.totalPages ?? 1
    const lastPage = resultList.data?.totalPages
    // A deletion can leave the current page past the end of the list.
    if (lastPage !== undefined && page > lastPage) setPage(lastPage)
    const classList = useResource(getAllStudentClasses)
    const classes = classList.data ?? []
    const [viewMode, setViewMode] = useState<ResultsViewMode>(storedResultsView)
    const [selectedResult, setSelectedResult] = useState<QuizSession | null>(
        null
    )
    const [resultToDelete, setResultToDelete] = useState<QuizSession | null>(
        null
    )
    const [selectedParticipant, setSelectedParticipant] =
        useState<QuizParticipant | null>(null)
    const selectedResultId = selectedResult?.id
    const selectedParticipantId = selectedParticipant?.id
    const answerList = useResource(
        useCallback(
            () =>
                selectedResultId === undefined ||
                selectedParticipantId === undefined
                    ? Promise.resolve([])
                    : getParticipantAnswers(
                          selectedResultId,
                          selectedParticipantId
                      ),
            [selectedParticipantId, selectedResultId]
        )
    )
    const answers = answerList.isLoading ? [] : (answerList.data ?? [])
    // Drafts only hold what the teacher typed; other answers show their score.
    const [scoreDrafts, setScoreDrafts] = useState<Record<number, string>>({})
    const [feedbackDrafts, setFeedbackDrafts] = useState<
        Record<number, string>
    >({})
    const [gradingAnswerId, setGradingAnswerId] = useState<number | null>(null)
    const [gradeError, setGradeError] = useState<string | null>(null)
    const deleting = useAsyncAction(deleteSelectedResult, (caught) =>
        apiErrorMessage(caught, t, t("delete-result-error"))
    )
    const publishing = useAsyncAction(publishSelectedGrades, (caught) =>
        apiErrorMessage(caught, t, t("publish-grades-error"))
    )

    useEffect(() => {
        try {
            localStorage.setItem(RESULTS_VIEW_STORAGE_KEY, viewMode)
        } catch {
            // The preference remains valid for this session if storage is unavailable.
        }
    }, [viewMode])

    function updateResults(update: (result: QuizSession) => QuizSession) {
        resultList.setData(
            (current) =>
                current && { ...current, items: current.items.map(update) }
        )
    }

    const dateFormatter = useMemo(
        () =>
            new Intl.DateTimeFormat(i18n.language, {
                dateStyle: "long",
                timeStyle: "short",
            }),
        [i18n.language]
    )

    function resultDate(result: QuizSession) {
        return dateFormatter.format(resultStart(result))
    }

    async function deleteSelectedResult(): Promise<void> {
        if (!resultToDelete) return
        await deleteQuizSession(resultToDelete.id)
        resultList.setData(
            (current) =>
                current && {
                    ...current,
                    items: current.items.filter(
                        (result) => result.id !== resultToDelete.id
                    ),
                }
        )
        if (selectedResult?.id === resultToDelete.id) setSelectedResult(null)
        setResultToDelete(null)
        resultList.reload()
    }

    function openParticipantAnswers(participant: QuizParticipant): void {
        if (participant.id === selectedParticipantId) answerList.reload()
        setSelectedParticipant(participant)
        setScoreDrafts({})
        setFeedbackDrafts({})
        setGradeError(null)
    }

    async function handleGrade(answer: QuizAnswerReview): Promise<void> {
        if (!selectedResult || selectedResult.grades_published_at !== null)
            return
        const score = Number(scoreDrafts[answer.id] ?? answer.score)
        if (!Number.isFinite(score)) return
        const feedback = feedbackDrafts[answer.id] ?? answer.feedback ?? ""
        setGradingAnswerId(answer.id)
        setGradeError(null)
        try {
            const graded = await gradeWrittenAnswer(
                selectedResult.id,
                answer.id,
                score,
                feedback
            )
            const scoreDifference = graded.score - answer.score
            const pendingDifference = answer.is_graded ? 0 : -1
            answerList.setData((current) =>
                current?.map((item) => (item.id === graded.id ? graded : item))
            )
            const updateSession = (session: QuizSession): QuizSession => ({
                ...session,
                participants: session.participants.map((participant) =>
                    participant.id === selectedParticipant?.id
                        ? {
                              ...participant,
                              score: roundScore(
                                  participant.score + scoreDifference
                              ),
                              pending_manual_grading_count:
                                  participant.pending_manual_grading_count +
                                  pendingDifference,
                          }
                        : participant
                ),
            })
            setSelectedResult((current) =>
                current ? updateSession(current) : current
            )
            updateResults((result) =>
                result.id === selectedResult.id ? updateSession(result) : result
            )
        } catch (caught) {
            setGradeError(apiErrorMessage(caught, t, t("answers-load-error")))
        } finally {
            setGradingAnswerId(null)
        }
    }

    async function publishSelectedGrades(): Promise<void> {
        if (!selectedResult) return
        const published = await publishQuizGrades(selectedResult.id)
        setSelectedResult(published)
        updateResults((result) =>
            result.id === published.id ? published : result
        )
    }

    if (!resultList.hasSettled) {
        return (
            <div
                className="flex min-h-64 items-center justify-center"
                role="status"
                aria-label={t("page-loading")}
            >
                <LoaderCircle
                    className="size-8 animate-spin text-primary motion-reduce:animate-none"
                    aria-hidden="true"
                />
            </div>
        )
    }

    if (resultList.error) {
        return (
            <div
                className="mt-6 rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive"
                role="alert"
            >
                {t("results-load-error")}
            </div>
        )
    }

    return (
        <>
            <div className="mt-6 grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
                <aside className="h-fit rounded-xl border bg-background p-4">
                    <h3 className="font-semibold">{t("filters")}</h3>
                    <FieldGroup className="mt-4 gap-4">
                        <Field>
                            <FieldLabel htmlFor="result-quiz-filter">
                                {t("quiz-title")}
                            </FieldLabel>
                            <Input
                                id="result-quiz-filter"
                                value={quizFilter}
                                placeholder={t("search-quiz")}
                                onChange={(event) => {
                                    setQuizFilter(event.target.value)
                                    setPage(1)
                                }}
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="result-class-filter">
                                {t("class-name")}
                            </FieldLabel>
                            <select
                                id="result-class-filter"
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={classFilter}
                                disabled={classList.isLoading}
                                onChange={(event) => {
                                    setClassFilter(event.target.value)
                                    setPage(1)
                                }}
                            >
                                <option value="">{t("all-classes")}</option>
                                {classes.map((studentClass) => (
                                    <option
                                        key={studentClass.id}
                                        value={studentClass.name}
                                    >
                                        {formatClassName(
                                            studentClass.grade_level,
                                            studentClass.name
                                        )}
                                    </option>
                                ))}
                            </select>
                        </Field>
                        {(quizFilter || classFilter) && (
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                    setQuizFilter("")
                                    setClassFilter("")
                                    setPage(1)
                                }}
                            >
                                {t("clear-filters")}
                            </Button>
                        )}
                    </FieldGroup>
                </aside>
                <div className="min-w-0">
                    <div className="mb-4 flex min-h-8 items-center justify-between gap-3">
                        <h3 className="font-semibold">{t("results")}</h3>
                        {results.length > 0 && (
                            <div
                                className="flex gap-1"
                                role="group"
                                aria-label={t("results-view")}
                            >
                                <Button
                                    type="button"
                                    size="sm"
                                    variant={
                                        viewMode === "cards"
                                            ? "default"
                                            : "outline"
                                    }
                                    aria-pressed={viewMode === "cards"}
                                    onClick={() => setViewMode("cards")}
                                >
                                    <LayoutGrid />
                                    {t("results-card-view")}
                                </Button>
                                <Button
                                    type="button"
                                    size="sm"
                                    variant={
                                        viewMode === "schedule"
                                            ? "default"
                                            : "outline"
                                    }
                                    aria-pressed={viewMode === "schedule"}
                                    onClick={() => setViewMode("schedule")}
                                >
                                    <CalendarRange />
                                    {t("results-schedule-view")}
                                </Button>
                            </div>
                        )}
                    </div>
                    {results.length === 0 ? (
                        <div className="flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed p-8 text-center">
                            <ChartColumn className="size-12 text-muted-foreground/60" />
                            <h3 className="mt-4 text-lg font-semibold">
                                {t("results-empty")}
                            </h3>
                            <p className="mt-1 max-w-md text-sm text-muted-foreground">
                                {t("results-empty-help")}
                            </p>
                        </div>
                    ) : (
                        <>
                            {viewMode === "schedule" ? (
                                <ResultsSchedule
                                    key={results
                                        .map((result) => result.id)
                                        .join(",")}
                                    results={results}
                                    locale={i18n.language}
                                    onSelect={setSelectedResult}
                                />
                            ) : (
                                <div
                                    key={results
                                        .map((result) => result.id)
                                        .join(",")}
                                    className="grid animate-in gap-4 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none md:grid-cols-2 xl:grid-cols-3"
                                >
                                    {results.map((result) => (
                                        <article
                                            key={result.id}
                                            className="flex flex-col rounded-2xl border bg-background p-5 shadow-sm transition-shadow hover:shadow-md"
                                        >
                                            <div className="flex items-center gap-3">
                                                <div
                                                    role="img"
                                                    aria-label={t(
                                                        result.grades_published_at
                                                            ? "grades-published"
                                                            : "grades-not-published"
                                                    )}
                                                    className={cn(
                                                        "shrink-0 rounded-xl p-2.5",
                                                        result.grades_published_at
                                                            ? "bg-success/10 text-success"
                                                            : "bg-warning/10 text-warning"
                                                    )}
                                                >
                                                    {result.grades_published_at ? (
                                                        <CheckCircle2
                                                            className="size-5"
                                                            aria-hidden="true"
                                                        />
                                                    ) : (
                                                        <TriangleAlert
                                                            className="size-5"
                                                            aria-hidden="true"
                                                        />
                                                    )}
                                                </div>
                                                <h3 className="min-w-0 flex-1 truncate text-lg font-bold">
                                                    {result.quiz_title}
                                                </h3>
                                                <span className="shrink-0 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold whitespace-nowrap text-primary">
                                                    {t("result-students", {
                                                        count: result.participant_count,
                                                    })}
                                                </span>
                                            </div>
                                            <div className="mt-3 space-y-2 text-sm text-muted-foreground">
                                                <p className="flex items-center gap-2">
                                                    <CalendarDays className="size-4 shrink-0" />
                                                    {resultDate(result)}
                                                </p>
                                                <p className="flex items-center gap-2">
                                                    <School className="size-4 shrink-0" />
                                                    {result.class_name}
                                                </p>
                                            </div>
                                            <div className="mt-5 flex gap-2">
                                                <Button
                                                    className="flex-1"
                                                    variant="outline"
                                                    onClick={() =>
                                                        setSelectedResult(
                                                            result
                                                        )
                                                    }
                                                >
                                                    <Eye />
                                                    {t("view-results")}
                                                </Button>
                                                <Button
                                                    variant="outline"
                                                    aria-label={t(
                                                        "delete-result"
                                                    )}
                                                    onClick={() => {
                                                        deleting.setError(null)
                                                        setResultToDelete(
                                                            result
                                                        )
                                                    }}
                                                >
                                                    <Trash2 />
                                                </Button>
                                            </div>
                                        </article>
                                    ))}
                                </div>
                            )}
                            <Pagination
                                currentPage={page}
                                totalPages={totalPages}
                                onPageChange={setPage}
                            />
                        </>
                    )}
                </div>
            </div>

            <ResultsExportDialog
                open={isExportDialogOpen}
                onOpenChange={onExportDialogOpenChange}
                classes={classes}
                areClassesLoading={classList.isLoading}
                classesFailed={Boolean(classList.error)}
            />

            <Dialog
                open={selectedResult !== null}
                onOpenChange={(open) => {
                    if (!open) setSelectedResult(null)
                }}
                title={selectedResult?.quiz_title ?? t("results")}
                description={
                    selectedResult
                        ? `${selectedResult.class_name} · ${resultDate(selectedResult)}`
                        : undefined
                }
                size="xl"
            >
                {selectedResult && (
                    <div className="space-y-4">
                        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-muted/40 p-4">
                            <div>
                                <p className="font-semibold">
                                    {t(
                                        selectedResult.grades_published_at
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
                                    selectedResult.grades_published_at !==
                                        null ||
                                    selectedResult.participants.some(
                                        (participant) =>
                                            participant.pending_manual_grading_count >
                                            0
                                    ) ||
                                    publishing.isPending
                                }
                                onClick={() => void publishing.run()}
                            >
                                {publishing.isPending && (
                                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                )}
                                {t(
                                    selectedResult.grades_published_at
                                        ? "grades-published"
                                        : "publish-grades"
                                )}
                            </Button>
                            {publishing.error && (
                                <p
                                    className="w-full text-sm text-destructive"
                                    role="alert"
                                >
                                    {publishing.error}
                                </p>
                            )}
                        </div>
                        <div className="grid gap-3 sm:grid-cols-3">
                            <div className="rounded-xl bg-muted p-4">
                                <p className="text-xs font-medium text-muted-foreground">
                                    {t("result-participants")}
                                </p>
                                <p className="mt-1 font-semibold">
                                    {selectedResult.participant_count}
                                </p>
                            </div>
                            <div className="rounded-xl bg-muted p-4">
                                <p className="text-xs font-medium text-muted-foreground">
                                    {t("result-median-maximum")}
                                </p>
                                <p className="mt-1 font-semibold">
                                    {formatScore(
                                        selectedResult.median_maximum_score,
                                        i18n.language
                                    )}{" "}
                                    {t("points-short")}
                                </p>
                            </div>
                            <div className="rounded-xl bg-muted p-4">
                                <p className="text-xs font-medium text-muted-foreground">
                                    {t("quiz-question-count")}
                                </p>
                                <p className="mt-1 font-semibold">
                                    {selectedResult.total_questions}
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
                                    {selectedResult.participants.map(
                                        (participant) => (
                                            <div
                                                key={participant.id}
                                                data-participant-id={
                                                    participant.id
                                                }
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
                                                                    selectedResult.median_maximum_score
                                                            ) >= 3 && (
                                                                <ResultIndicator
                                                                    label={t(
                                                                        "result-maximum-median-gap",
                                                                        {
                                                                            maximum:
                                                                                formatScore(
                                                                                    participant.maximum_score,
                                                                                    i18n.language
                                                                                ),
                                                                            median: formatScore(
                                                                                selectedResult.median_maximum_score,
                                                                                i18n.language
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
                                                        {t("result-progress")}{" "}
                                                        :{" "}
                                                    </span>
                                                    {participant.answered_count}{" "}
                                                    /{" "}
                                                    {
                                                        selectedResult.total_questions
                                                    }
                                                </p>
                                                <div
                                                    data-participant-score
                                                    className="flex items-center justify-between gap-2 text-end font-bold text-primary tabular-nums md:justify-end md:whitespace-nowrap"
                                                >
                                                    <span className="font-normal text-foreground md:hidden">
                                                        {t(
                                                            "result-score-total"
                                                        )}{" "}
                                                        :{" "}
                                                    </span>
                                                    <span className="inline-flex items-center justify-end gap-1">
                                                        <Grade
                                                            score={
                                                                participant.score
                                                            }
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
                                                            openParticipantAnswers(
                                                                participant
                                                            )
                                                        }
                                                    >
                                                        <FileText />
                                                        {t("view-answers")}
                                                    </Button>
                                                </div>
                                            </div>
                                        )
                                    )}
                                    {selectedResult.participants.length ===
                                        0 && (
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

            <ParticipantAnswersDialog
                participant={selectedParticipant}
                answers={answers}
                isLoading={selectedParticipant !== null && answerList.isLoading}
                error={
                    gradeError ??
                    (answerList.error
                        ? apiErrorMessage(
                              answerList.error,
                              t,
                              t("answers-load-error")
                          )
                        : null)
                }
                scoreDrafts={Object.fromEntries(
                    answers.map((answer) => [
                        answer.id,
                        scoreDrafts[answer.id] ?? String(answer.score),
                    ])
                )}
                feedbackDrafts={Object.fromEntries(
                    answers.map((answer) => [
                        answer.id,
                        feedbackDrafts[answer.id] ?? answer.feedback ?? "",
                    ])
                )}
                gradingAnswerId={gradingAnswerId}
                isReadOnly={selectedResult?.grades_published_at != null}
                locale={i18n.language}
                onClose={() => {
                    setSelectedParticipant(null)
                    setGradeError(null)
                }}
                onScoreDraftChange={(answerId, score) =>
                    setScoreDrafts((current) => ({
                        ...current,
                        [answerId]: score,
                    }))
                }
                onFeedbackDraftChange={(answerId, feedback) =>
                    setFeedbackDrafts((current) => ({
                        ...current,
                        [answerId]: feedback,
                    }))
                }
                onGrade={(answer) => void handleGrade(answer)}
            />

            <Dialog
                open={resultToDelete !== null}
                onOpenChange={(open) => {
                    if (!open && !deleting.isPending) setResultToDelete(null)
                }}
                title={t("delete-result")}
                description={t("delete-result-help", {
                    title: resultToDelete?.quiz_title,
                })}
                size="sm"
            >
                <div className="space-y-4">
                    {deleting.error && (
                        <p className="text-sm text-destructive" role="alert">
                            {deleting.error}
                        </p>
                    )}
                    <div className="flex justify-end gap-2">
                        <Button
                            variant="outline"
                            onClick={() => setResultToDelete(null)}
                            disabled={deleting.isPending}
                        >
                            {t("cancel")}
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={() => void deleting.run()}
                            disabled={deleting.isPending}
                        >
                            {deleting.isPending ? (
                                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                            ) : (
                                <Trash2 />
                            )}
                            {t("delete")}
                        </Button>
                    </div>
                </div>
            </Dialog>
        </>
    )
}

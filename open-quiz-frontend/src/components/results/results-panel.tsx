import { deleteQuizSession, publishQuizGrades } from "@/api/quizzes"
import { getAllStudentClasses } from "@/api/classes"
import type { QuizParticipant, QuizSession } from "@/api/types"
import { ParticipantAnswersDialog } from "@/components/results/participant-answers-dialog"
import { ResultCard, ResultFilters } from "@/components/results/result-card"
import { ResultDetailsDialog } from "@/components/results/result-details-dialog"
import { ResultsExportDialog } from "@/components/results/results-export-dialog"
import { ResultsSchedule } from "@/components/results/results-schedule"
import { resultStart } from "@/components/results/results-utils"
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog"
import { Pagination } from "@/components/ui/pagination"
import { ChartColumn } from "lucide-react"
import { useCallback, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { useLocale } from "@/lib/locale"
import { apiErrorMessage } from "@/lib/errors"
import { useAsyncAction } from "@/hooks/use-async-action"
import { usePagedList } from "@/hooks/use-paged-list"
import { usePersistentState } from "@/hooks/use-persistent-state"
import { useResource } from "@/hooks/use-resource"
import { loadResults, loadScheduleWeek } from "./results-loading"
import { ResultsViewToggle } from "./results-view-toggle"
import { useWrittenAnswerGrading } from "./use-written-answer-grading"
import { LoadingState } from "@/components/ui/loading-state"
import { AnimatedGrid } from "@/components/ui/animated-grid"

const RESULTS_VIEWS = ["cards", "schedule"] as const

const RESULTS_VIEW_STORAGE_KEY = "open-quiz-teacher-results-view"

type ResultsPanelProps = {
    isExportDialogOpen: boolean
    onExportDialogOpenChange: (open: boolean) => void
}

export function ResultsPanel({
    isExportDialogOpen,
    onExportDialogOpenChange,
}: ResultsPanelProps) {
    const { t } = useTranslation()
    const locale = useLocale()
    const resultList = usePagedList(loadResults, { quiz: "", class: "" })
    const results = resultList.items
    const classList = useResource(getAllStudentClasses)
    const classes = classList.data ?? []
    const [viewMode, setViewMode] = usePersistentState(
        RESULTS_VIEW_STORAGE_KEY,
        RESULTS_VIEWS,
        "cards"
    )
    // The week the teacher moved to, or null for the newest one.
    const [scheduleWeek, setScheduleWeek] = useState<Date | null>(null)
    const resultFilters = resultList.filters
    const schedule = useResource(
        useCallback(
            (signal: AbortSignal) =>
                viewMode === "schedule"
                    ? loadScheduleWeek(resultFilters, scheduleWeek, signal)
                    : Promise.resolve(null),
            [resultFilters, scheduleWeek, viewMode]
        )
    )
    const [selectedResult, setSelectedResult] = useState<QuizSession | null>(
        null
    )
    const [resultToDelete, setResultToDelete] = useState<QuizSession | null>(
        null
    )
    const [selectedParticipant, setSelectedParticipant] =
        useState<QuizParticipant | null>(null)
    const grading = useWrittenAnswerGrading(
        selectedResult,
        selectedParticipant,
        (update) => {
            setSelectedResult((current) => current && update(current))
            updateResults(update)
        }
    )
    const deleting = useAsyncAction(deleteSelectedResult, (caught) =>
        apiErrorMessage(caught, t, t("delete-result-error"))
    )
    const publishing = useAsyncAction(publishSelectedGrades, (caught) =>
        apiErrorMessage(caught, t, t("publish-grades-error"))
    )

    function updateResults(update: (result: QuizSession) => QuizSession) {
        resultList.setData(
            (current) =>
                current && { ...current, items: current.items.map(update) }
        )
        schedule.setData(
            (current) =>
                current && { ...current, results: current.results.map(update) }
        )
    }

    const dateFormatter = useMemo(
        () =>
            new Intl.DateTimeFormat(locale, {
                dateStyle: "long",
                timeStyle: "short",
            }),
        [locale]
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
        schedule.reload()
    }

    function openParticipantAnswers(participant: QuizParticipant): void {
        if (participant.id === selectedParticipant?.id) grading.reload()
        setSelectedParticipant(participant)
        grading.reset()
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
        return <LoadingState className="min-h-64" size={8} />
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
                <ResultFilters
                    filters={resultList.filters}
                    classes={classes}
                    areClassesLoading={classList.isLoading}
                    onFilterChange={(name, value) => {
                        setScheduleWeek(null)
                        resultList.setFilter(name, value)
                    }}
                    onReset={() => {
                        setScheduleWeek(null)
                        resultList.resetFilters()
                    }}
                />
                <div className="min-w-0">
                    <div className="mb-4 flex min-h-8 items-center justify-between gap-3">
                        <h3 className="font-semibold">{t("results")}</h3>
                        {results.length > 0 && (
                            <ResultsViewToggle
                                value={viewMode}
                                onChange={setViewMode}
                            />
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
                                schedule.error ? (
                                    <p
                                        className="rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive"
                                        role="alert"
                                    >
                                        {t("results-load-error")}
                                    </p>
                                ) : schedule.data ? (
                                    <ResultsSchedule
                                        weekStart={schedule.data.weekStart}
                                        results={schedule.data.results}
                                        hasEarlier={schedule.data.hasEarlier}
                                        hasLater={schedule.data.hasLater}
                                        locale={locale}
                                        onWeekChange={setScheduleWeek}
                                        onSelect={setSelectedResult}
                                    />
                                ) : (
                                    <LoadingState
                                        className="min-h-64"
                                        size={8}
                                    />
                                )
                            ) : (
                                <AnimatedGrid
                                    ids={results.map((result) => result.id)}
                                    className="gap-4 md:grid-cols-2 xl:grid-cols-3"
                                >
                                    {results.map((result) => (
                                        <ResultCard
                                            key={result.id}
                                            result={result}
                                            date={resultDate(result)}
                                            onView={() =>
                                                setSelectedResult(result)
                                            }
                                            onDelete={() => {
                                                deleting.setError(null)
                                                setResultToDelete(result)
                                            }}
                                        />
                                    ))}
                                </AnimatedGrid>
                            )}
                            {viewMode === "cards" && (
                                <Pagination
                                    currentPage={resultList.page}
                                    totalPages={resultList.totalPages}
                                    onPageChange={resultList.showPage}
                                />
                            )}
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

            <ResultDetailsDialog
                result={selectedResult}
                description={
                    selectedResult
                        ? `${selectedResult.class_name} · ${resultDate(selectedResult)}`
                        : undefined
                }
                locale={locale}
                isPublishing={publishing.isPending}
                publishError={publishing.error}
                onPublish={() => void publishing.run()}
                onOpenParticipant={openParticipantAnswers}
                onClose={() => setSelectedResult(null)}
            />

            <ParticipantAnswersDialog
                participant={selectedParticipant}
                answers={grading.answers}
                isLoading={selectedParticipant !== null && grading.isLoading}
                error={grading.error}
                scoreDrafts={grading.scoreDrafts}
                feedbackDrafts={grading.feedbackDrafts}
                gradingAnswerId={grading.gradingAnswerId}
                isReadOnly={selectedResult?.grades_published_at != null}
                locale={locale}
                onClose={() => {
                    setSelectedParticipant(null)
                    grading.reset()
                }}
                onScoreDraftChange={grading.setScoreDraft}
                onFeedbackDraftChange={grading.setFeedbackDraft}
                onGrade={(answer) => void grading.grade(answer)}
            />

            <ConfirmDeleteDialog
                open={resultToDelete !== null}
                title={t("delete-result")}
                description={t("delete-result-help", {
                    title: resultToDelete?.quiz_title,
                })}
                isBusy={deleting.isPending}
                error={deleting.error}
                onClose={() => setResultToDelete(null)}
                onConfirm={() => void deleting.run()}
            />
        </>
    )
}

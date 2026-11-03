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
import { ResultCard, ResultFilters } from "@/components/results/result-card"
import { ResultDetailsDialog } from "@/components/results/result-details-dialog"
import { ResultsExportDialog } from "@/components/results/results-export-dialog"
import { ResultsSchedule } from "@/components/results/results-schedule"
import { resultStart } from "@/components/results/results-utils"
import { Button } from "@/components/ui/button"
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog"
import { Pagination } from "@/components/ui/pagination"
import {
    CalendarRange,
    ChartColumn,
    LoaderCircle,
    LayoutGrid,
} from "lucide-react"
import { useCallback, useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { apiErrorMessage } from "@/lib/errors"
import { useAsyncAction } from "@/hooks/use-async-action"
import { usePagedList } from "@/hooks/use-paged-list"
import { useResource } from "@/hooks/use-resource"

type ResultsViewMode = "cards" | "schedule"

const RESULTS_VIEW_STORAGE_KEY = "open-quiz-teacher-results-view"

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

function loadResults(page: number, filters: { quiz: string; class: string }) {
    return getQuizResults(page, filters.quiz.trim(), filters.class.trim())
}

export function ResultsPanel({
    isExportDialogOpen,
    onExportDialogOpenChange,
}: ResultsPanelProps) {
    const { t, i18n } = useTranslation()
    const resultList = usePagedList(loadResults, { quiz: "", class: "" })
    const results = resultList.items
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
                <ResultFilters
                    filters={resultList.filters}
                    classes={classes}
                    areClassesLoading={classList.isLoading}
                    onFilterChange={resultList.setFilter}
                    onReset={resultList.resetFilters}
                />
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
                                </div>
                            )}
                            <Pagination
                                currentPage={resultList.page}
                                totalPages={resultList.totalPages}
                                onPageChange={resultList.showPage}
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

            <ResultDetailsDialog
                result={selectedResult}
                description={
                    selectedResult
                        ? `${selectedResult.class_name} · ${resultDate(selectedResult)}`
                        : undefined
                }
                locale={i18n.language}
                isPublishing={publishing.isPending}
                publishError={publishing.error}
                onPublish={() => void publishing.run()}
                onOpenParticipant={openParticipantAnswers}
                onClose={() => setSelectedResult(null)}
            />

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

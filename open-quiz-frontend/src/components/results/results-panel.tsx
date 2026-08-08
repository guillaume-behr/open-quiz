import {
    deleteQuizSession,
    downloadQuizResults,
    getAllQuizzes,
    getParticipantAnswers,
    getQuizResults,
    gradeWrittenAnswer,
    publishQuizGrades,
} from "@/api/quizzes"
import { getAllStudentClasses } from "@/api/classes"
import type {
    Quiz,
    QuizAnswerReview,
    QuizParticipant,
    QuizSession,
    StudentClass,
} from "@/api/types"
import { ParticipantAnswersDialog } from "@/components/results/participant-answers-dialog"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Pagination } from "@/components/ui/pagination"
import {
    CalendarDays,
    ChartColumn,
    CheckCircle2,
    Download,
    Eye,
    FileText,
    LoaderCircle,
    School,
    Trash2,
    TriangleAlert,
    UserRound,
} from "lucide-react"
import { useEffect, useMemo, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

function formatScore(score: number, locale: string) {
    return new Intl.NumberFormat(locale, {
        maximumFractionDigits: 2,
    }).format(score)
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
    const answersRequestVersion = useRef(0)
    const [results, setResults] = useState<QuizSession[]>([])
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)
    const [reloadKey, setReloadKey] = useState(0)
    const [quizFilter, setQuizFilter] = useState("")
    const [classFilter, setClassFilter] = useState("")
    const [selectedResult, setSelectedResult] = useState<QuizSession | null>(
        null
    )
    const [isLoading, setIsLoading] = useState(true)
    const [loadError, setLoadError] = useState(false)
    const [resultToDelete, setResultToDelete] = useState<QuizSession | null>(
        null
    )
    const [isDeleting, setIsDeleting] = useState(false)
    const [deleteError, setDeleteError] = useState(false)
    const [selectedParticipant, setSelectedParticipant] =
        useState<QuizParticipant | null>(null)
    const [answers, setAnswers] = useState<QuizAnswerReview[]>([])
    const [areAnswersLoading, setAreAnswersLoading] = useState(false)
    const [answersError, setAnswersError] = useState(false)
    const [scoreDrafts, setScoreDrafts] = useState<Record<number, string>>({})
    const [gradingAnswerId, setGradingAnswerId] = useState<number | null>(null)
    const [publishingSessionId, setPublishingSessionId] = useState<
        number | null
    >(null)
    const [publishError, setPublishError] = useState(false)
    const [exportClasses, setExportClasses] = useState<StudentClass[]>([])
    const [areClassesLoading, setAreClassesLoading] = useState(true)
    const [exportQuizzes, setExportQuizzes] = useState<Quiz[]>([])
    const [exportClassId, setExportClassId] = useState<number | null>(null)
    const [exportQuizId, setExportQuizId] = useState<number | null>(null)
    const [isExportLoading, setIsExportLoading] = useState(false)
    const [isExporting, setIsExporting] = useState(false)
    const [exportError, setExportError] = useState(false)
    useEffect(() => {
        let isActive = true
        getQuizResults(page, quizFilter.trim(), classFilter.trim())
            .then((result) => {
                if (!isActive) return
                setResults(result.items)
                setTotalPages(result.totalPages)
                setLoadError(false)
                if (result.page > result.totalPages) setPage(result.totalPages)
            })
            .catch(() => {
                if (isActive) setLoadError(true)
            })
            .finally(() => {
                if (isActive) setIsLoading(false)
            })
        return () => {
            isActive = false
        }
    }, [classFilter, page, quizFilter, reloadKey])

    useEffect(() => {
        let isActive = true
        getAllStudentClasses()
            .then((classes) => {
                if (!isActive) return
                setExportClasses(classes)
                setExportClassId(classes[0]?.id ?? null)
            })
            .catch(() => {
                if (isActive) setExportError(true)
            })
            .finally(() => {
                if (isActive) setAreClassesLoading(false)
            })
        return () => {
            isActive = false
        }
    }, [])

    useEffect(() => {
        if (!isExportDialogOpen || exportQuizzes.length > 0) return
        let isActive = true
        Promise.resolve()
            .then(() => {
                if (!isActive) return Promise.reject(new Error("cancelled"))
                setExportError(false)
                setIsExportLoading(true)
                return getAllQuizzes()
            })
            .then((quizzes) => {
                if (!isActive) return
                setExportQuizzes(quizzes)
            })
            .catch(() => {
                if (isActive) setExportError(true)
            })
            .finally(() => {
                if (isActive) setIsExportLoading(false)
            })
        return () => {
            isActive = false
        }
    }, [exportQuizzes.length, isExportDialogOpen])

    async function handleExport(): Promise<void> {
        if (exportClassId === null) return
        setIsExporting(true)
        setExportError(false)
        try {
            const blob = await downloadQuizResults(exportClassId, exportQuizId)
            const url = URL.createObjectURL(blob)
            const link = document.createElement("a")
            link.href = url
            link.download = `resultats-classe-${exportClassId}${exportQuizId === null ? "-tous-les-quiz" : `-quiz-${exportQuizId}`}.csv`
            document.body.appendChild(link)
            link.click()
            link.remove()
            window.setTimeout(() => URL.revokeObjectURL(url), 0)
            onExportDialogOpenChange(false)
        } catch {
            setExportError(true)
        } finally {
            setIsExporting(false)
        }
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
        return dateFormatter.format(
            new Date(result.started_at ?? result.created_at)
        )
    }

    async function handleDeleteResult() {
        if (!resultToDelete) return
        setIsDeleting(true)
        setDeleteError(false)
        try {
            await deleteQuizSession(resultToDelete.id)
            setResults((existing) =>
                existing.filter((result) => result.id !== resultToDelete.id)
            )
            if (selectedResult?.id === resultToDelete.id) {
                setSelectedResult(null)
            }
            setResultToDelete(null)
            setReloadKey((current) => current + 1)
        } catch {
            setDeleteError(true)
        } finally {
            setIsDeleting(false)
        }
    }

    async function openParticipantAnswers(
        participant: QuizParticipant
    ): Promise<void> {
        if (!selectedResult) return
        const requestVersion = ++answersRequestVersion.current
        setSelectedParticipant(participant)
        setAreAnswersLoading(true)
        setAnswersError(false)
        try {
            const loadedAnswers = await getParticipantAnswers(
                selectedResult.id,
                participant.id
            )
            if (requestVersion !== answersRequestVersion.current) return
            setAnswers(loadedAnswers)
            setScoreDrafts(
                Object.fromEntries(
                    loadedAnswers.map((answer) => [
                        answer.id,
                        String(answer.score),
                    ])
                )
            )
        } catch {
            if (requestVersion === answersRequestVersion.current) {
                setAnswersError(true)
            }
        } finally {
            if (requestVersion === answersRequestVersion.current) {
                setAreAnswersLoading(false)
            }
        }
    }

    async function handleGrade(answer: QuizAnswerReview): Promise<void> {
        if (!selectedResult) return
        const score = Number(scoreDrafts[answer.id])
        if (!Number.isFinite(score)) return
        setGradingAnswerId(answer.id)
        setAnswersError(false)
        try {
            const graded = await gradeWrittenAnswer(
                selectedResult.id,
                answer.id,
                score
            )
            const scoreDifference = graded.score - answer.score
            const pendingDifference = answer.is_graded ? 0 : -1
            setAnswers((current) =>
                current.map((item) => (item.id === graded.id ? graded : item))
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
            setResults((current) =>
                current.map((result) =>
                    result.id === selectedResult.id
                        ? updateSession(result)
                        : result
                )
            )
        } catch {
            setAnswersError(true)
        } finally {
            setGradingAnswerId(null)
        }
    }

    async function handlePublishGrades(): Promise<void> {
        if (!selectedResult) return
        setPublishingSessionId(selectedResult.id)
        setPublishError(false)
        try {
            const published = await publishQuizGrades(selectedResult.id)
            setSelectedResult(published)
            setResults((current) =>
                current.map((result) =>
                    result.id === published.id ? published : result
                )
            )
        } catch {
            setPublishError(true)
        } finally {
            setPublishingSessionId(null)
        }
    }

    if (isLoading) {
        return (
            <div className="flex min-h-64 items-center justify-center">
                <LoaderCircle className="size-8 animate-spin text-primary" />
            </div>
        )
    }

    if (loadError) {
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
                                className="h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                                value={classFilter}
                                disabled={areClassesLoading}
                                onChange={(event) => {
                                    setClassFilter(event.target.value)
                                    setPage(1)
                                }}
                            >
                                <option value="">{t("all-classes")}</option>
                                {exportClasses.map((studentClass) => (
                                    <option
                                        key={studentClass.id}
                                        value={studentClass.name}
                                    >
                                        {studentClass.name}
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
                    <div>
                        <div
                            key={results.map((result) => result.id).join(",")}
                            className="grid animate-in gap-4 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none md:grid-cols-2 xl:grid-cols-3"
                        >
                            {results.map((result) => (
                                <article
                                    key={result.id}
                                    className="flex flex-col rounded-2xl border bg-background p-5 shadow-sm transition-shadow hover:shadow-md"
                                >
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="rounded-xl bg-primary/10 p-3 text-primary">
                                            <CheckCircle2 className="size-5" />
                                        </div>
                                        <span className="rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary">
                                            {t("result-students", {
                                                count: result.participant_count,
                                            })}
                                        </span>
                                    </div>
                                    <h3 className="mt-4 text-lg font-bold">
                                        {result.quiz_title}
                                    </h3>
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
                                                setSelectedResult(result)
                                            }
                                        >
                                            <Eye />
                                            {t("view-results")}
                                        </Button>
                                        <Button
                                            variant="outline"
                                            aria-label={t("delete-result")}
                                            onClick={() => {
                                                setDeleteError(false)
                                                setResultToDelete(result)
                                            }}
                                        >
                                            <Trash2 />
                                        </Button>
                                    </div>
                                </article>
                            ))}
                        </div>
                        <Pagination
                            currentPage={page}
                            totalPages={totalPages}
                            onPageChange={setPage}
                        />
                    </div>
                )}
            </div>

            <Dialog
                open={isExportDialogOpen}
                onOpenChange={(open) => {
                    if (!isExporting) onExportDialogOpenChange(open)
                }}
                title={t("export-results-csv")}
                description={t("export-results-help")}
            >
                {isExportLoading || areClassesLoading ? (
                    <div className="flex min-h-32 items-center justify-center">
                        <LoaderCircle className="size-7 animate-spin text-primary" />
                    </div>
                ) : (
                    <FieldGroup>
                        <Field>
                            <FieldLabel htmlFor="export-results-class">
                                {t("class-name")}
                            </FieldLabel>
                            <select
                                id="export-results-class"
                                className="h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                                value={exportClassId ?? ""}
                                onChange={(event) =>
                                    setExportClassId(Number(event.target.value))
                                }
                            >
                                {exportClasses.map((studentClass) => (
                                    <option
                                        key={studentClass.id}
                                        value={studentClass.id}
                                    >
                                        {studentClass.name} —{" "}
                                        {studentClass.grade_level}
                                    </option>
                                ))}
                            </select>
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="export-results-quiz">
                                {t("quiz-title")}
                            </FieldLabel>
                            <select
                                id="export-results-quiz"
                                className="h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                                value={exportQuizId ?? ""}
                                onChange={(event) =>
                                    setExportQuizId(
                                        event.target.value
                                            ? Number(event.target.value)
                                            : null
                                    )
                                }
                            >
                                <option value="">{t("all-quizzes")}</option>
                                {exportQuizzes.map((quiz) => (
                                    <option key={quiz.id} value={quiz.id}>
                                        {quiz.title}
                                    </option>
                                ))}
                            </select>
                        </Field>
                        {exportClasses.length === 0 && !exportError && (
                            <p className="text-sm text-muted-foreground">
                                {t("export-results-no-classes")}
                            </p>
                        )}
                        {exportError && (
                            <p
                                className="text-sm text-destructive"
                                role="alert"
                            >
                                {t("export-results-error")}
                            </p>
                        )}
                        <div className="flex justify-end gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                disabled={isExporting}
                                onClick={() => onExportDialogOpenChange(false)}
                            >
                                {t("cancel")}
                            </Button>
                            <Button
                                type="button"
                                disabled={isExporting || exportClassId === null}
                                onClick={handleExport}
                            >
                                {isExporting ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <Download />
                                )}
                                {t("export-csv")}
                            </Button>
                        </div>
                    </FieldGroup>
                )}
            </Dialog>

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
                className="max-w-5xl"
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
                                    publishingSessionId === selectedResult.id
                                }
                                onClick={() => void handlePublishGrades()}
                            >
                                {publishingSessionId === selectedResult.id && (
                                    <LoaderCircle className="animate-spin" />
                                )}
                                {t(
                                    selectedResult.grades_published_at
                                        ? "grades-published"
                                        : "publish-grades"
                                )}
                            </Button>
                            {publishError && (
                                <p
                                    className="w-full text-sm text-destructive"
                                    role="alert"
                                >
                                    {t("publish-grades-error")}
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
                                <span className="text-right">
                                    {t("result-score-total")}
                                </span>
                                <span>{t("answers")}</span>
                            </div>
                            <div className="divide-y">
                                {selectedResult.participants.map(
                                    (participant) => (
                                        <div
                                            key={participant.id}
                                            className={`grid gap-3 px-4 py-4 md:grid-cols-[minmax(180px,1fr)_140px_180px_140px] md:items-center md:gap-4 ${participant.maximum_score > selectedResult.median_maximum_score ? "bg-amber-500/10" : ""}`}
                                        >
                                            <div className="flex min-w-0 items-center gap-3">
                                                <div className="rounded-full bg-primary/10 p-2 text-primary">
                                                    <UserRound className="size-4" />
                                                </div>
                                                <div className="min-w-0">
                                                    <p className="truncate font-semibold">
                                                        {participant.student_display_name ??
                                                            participant.student_identifier}
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
                                                {participant.answered_count} /{" "}
                                                {selectedResult.total_questions}
                                            </p>
                                            <p className="text-right font-bold text-primary tabular-nums md:whitespace-nowrap">
                                                <span className="font-normal text-foreground md:hidden">
                                                    {t("result-score-total")}{" "}
                                                    :{" "}
                                                </span>
                                                {formatScore(
                                                    participant.score,
                                                    i18n.language
                                                )}{" "}
                                                /{" "}
                                                {formatScore(
                                                    participant.maximum_score,
                                                    i18n.language
                                                )}{" "}
                                                {t("points-short")}
                                                {participant.maximum_score >
                                                    selectedResult.median_maximum_score && (
                                                    <span className="mt-1 flex items-center gap-1 text-xs font-semibold text-amber-700 dark:text-amber-300">
                                                        <TriangleAlert className="size-4 shrink-0" />
                                                        {t(
                                                            "result-maximum-above-median"
                                                        )}
                                                    </span>
                                                )}
                                            </p>
                                            <div>
                                                {participant.pending_manual_grading_count >
                                                    0 && (
                                                    <p className="mb-1 text-xs font-medium text-amber-700">
                                                        {t(
                                                            "answers-pending-grading",
                                                            {
                                                                count: participant.pending_manual_grading_count,
                                                            }
                                                        )}
                                                    </p>
                                                )}
                                                <Button
                                                    type="button"
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() =>
                                                        void openParticipantAnswers(
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
                                {selectedResult.participants.length === 0 && (
                                    <p className="p-6 text-center text-sm text-muted-foreground">
                                        {t("result-no-participants")}
                                    </p>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </Dialog>

            <ParticipantAnswersDialog
                participant={selectedParticipant}
                answers={answers}
                isLoading={areAnswersLoading}
                hasError={answersError}
                scoreDrafts={scoreDrafts}
                gradingAnswerId={gradingAnswerId}
                locale={i18n.language}
                onClose={() => {
                    setSelectedParticipant(null)
                    setAnswers([])
                    setAnswersError(false)
                }}
                onScoreDraftChange={(answerId, score) =>
                    setScoreDrafts((current) => ({
                        ...current,
                        [answerId]: score,
                    }))
                }
                onGrade={(answer) => void handleGrade(answer)}
            />

            <Dialog
                open={resultToDelete !== null}
                onOpenChange={(open) => {
                    if (!open && !isDeleting) setResultToDelete(null)
                }}
                title={t("delete-result")}
                description={t("delete-result-help", {
                    title: resultToDelete?.quiz_title,
                })}
            >
                <div className="space-y-4">
                    {deleteError && (
                        <p className="text-sm text-destructive" role="alert">
                            {t("delete-result-error")}
                        </p>
                    )}
                    <div className="flex justify-end gap-2">
                        <Button
                            variant="outline"
                            onClick={() => setResultToDelete(null)}
                            disabled={isDeleting}
                        >
                            {t("cancel")}
                        </Button>
                        <Button
                            variant="destructive"
                            onClick={() => void handleDeleteResult()}
                            disabled={isDeleting}
                        >
                            {isDeleting ? (
                                <LoaderCircle className="animate-spin" />
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

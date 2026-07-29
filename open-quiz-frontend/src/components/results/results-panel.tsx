import {
    deleteQuizSession,
    getParticipantAnswers,
    getQuizResults,
    gradeWrittenAnswer,
} from "@/api/quizzes"
import type {
    QuizAnswerReview,
    QuizParticipant,
    QuizSession,
} from "@/api/types"
import { ParticipantAnswersDialog } from "@/components/results/participant-answers-dialog"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    CalendarDays,
    ChartColumn,
    CheckCircle2,
    Eye,
    FileText,
    LoaderCircle,
    School,
    Trash2,
    UserRound,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"
import { useTranslation } from "react-i18next"

function formatScore(score: number, locale: string) {
    return new Intl.NumberFormat(locale, {
        maximumFractionDigits: 2,
    }).format(score)
}

export function ResultsPanel() {
    const { t, i18n } = useTranslation()
    const [results, setResults] = useState<QuizSession[]>([])
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

    useEffect(() => {
        let isActive = true
        getQuizResults()
            .then((sessions) => {
                if (isActive) setResults(sessions)
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
    }, [])

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
        setSelectedParticipant(participant)
        setAreAnswersLoading(true)
        setAnswersError(false)
        try {
            const loadedAnswers = await getParticipantAnswers(
                selectedResult.id,
                participant.id
            )
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
            setAnswersError(true)
        } finally {
            setAreAnswersLoading(false)
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
                              score: participant.score + scoreDifference,
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

    if (isLoading) {
        return (
            <div className="flex min-h-64 items-center justify-center">
                <LoaderCircle className="size-8 animate-spin text-primary" />
            </div>
        )
    }

    if (loadError) {
        return (
            <div className="mt-6 rounded-xl border border-destructive/30 bg-destructive/5 p-5 text-sm text-destructive">
                {t("results-load-error")}
            </div>
        )
    }

    return (
        <>
            {results.length === 0 ? (
                <div className="mt-6 flex min-h-64 flex-col items-center justify-center rounded-2xl border border-dashed p-8 text-center">
                    <ChartColumn className="size-12 text-muted-foreground/60" />
                    <h3 className="mt-4 text-lg font-semibold">
                        {t("results-empty")}
                    </h3>
                    <p className="mt-1 max-w-md text-sm text-muted-foreground">
                        {t("results-empty-help")}
                    </p>
                </div>
            ) : (
                <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-3">
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
                                    onClick={() => setSelectedResult(result)}
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
            )}

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
            >
                {selectedResult && (
                    <div className="space-y-4">
                        <div className="grid gap-3 sm:grid-cols-3">
                            <div className="rounded-xl bg-muted p-4">
                                <p className="text-xs font-medium text-muted-foreground">
                                    {t("class-name")}
                                </p>
                                <p className="mt-1 font-semibold">
                                    {selectedResult.class_name}
                                </p>
                            </div>
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
                                    {t("quiz-question-count")}
                                </p>
                                <p className="mt-1 font-semibold">
                                    {selectedResult.total_questions}
                                </p>
                            </div>
                        </div>

                        <div className="overflow-hidden rounded-xl border">
                            <div className="hidden grid-cols-[minmax(0,1fr)_140px_120px_auto] gap-4 border-b bg-muted/60 px-4 py-3 text-xs font-semibold text-muted-foreground sm:grid">
                                <span>{t("student-name")}</span>
                                <span>{t("result-progress")}</span>
                                <span>{t("result-score")}</span>
                                <span>{t("answers")}</span>
                            </div>
                            <div className="divide-y">
                                {selectedResult.participants.map(
                                    (participant) => (
                                        <div
                                            key={participant.id}
                                            className="grid gap-3 px-4 py-4 sm:grid-cols-[minmax(0,1fr)_140px_120px_auto] sm:items-center sm:gap-4"
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
                                                    <p className="truncate text-xs text-muted-foreground">
                                                        {
                                                            participant.student_identifier
                                                        }
                                                    </p>
                                                </div>
                                            </div>
                                            <p className="text-sm">
                                                <span className="sm:hidden">
                                                    {t("result-progress")}{" "}
                                                    :{" "}
                                                </span>
                                                {participant.answered_count} /{" "}
                                                {selectedResult.total_questions}
                                            </p>
                                            <p className="font-bold text-primary">
                                                <span className="font-normal text-foreground sm:hidden">
                                                    {t("result-score")} :{" "}
                                                </span>
                                                {formatScore(
                                                    participant.score,
                                                    i18n.language
                                                )}{" "}
                                                {t("points-short")}
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

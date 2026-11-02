import { getAllStudentClasses } from "@/api/classes"
import { ApiError, getLiveAccessToken } from "@/api/client"
import { getAllQuestionBanks } from "@/api/question-banks"
import {
    cancelQuizSession,
    createQuiz,
    deleteQuiz,
    deleteQuizSession,
    getAllQuizzes,
    getQuizzes,
    launchQuiz,
    pauseQuizSession,
    previewQuiz,
    resumeQuizSession,
    startQuizSession,
    updateQuiz,
} from "@/api/quizzes"
import type { GradeLevel, Quiz, QuizSession } from "@/api/types"
import { ActiveQuizSessionDialog } from "@/components/quizzes/active-quiz-session-dialog"
import { printExamSubjects } from "@/components/quizzes/print-quiz"
import { QuizFormDialog } from "@/components/quizzes/quiz-form-dialog"
import {
    availableQuestionCounts,
    emptyQuizForm,
    quizFormReducer,
} from "@/components/quizzes/quiz-form-state"
import {
    LaunchQuizDialog,
    PrintQuizDialog,
    QuizPreviewDialog,
    SessionActionDialog,
} from "@/components/quizzes/quiz-secondary-dialogs"
import { QuizzesList } from "@/components/quizzes/quizzes-list"
import { isActiveSessionStatus } from "@/lib/session-status"
import { connectLiveUpdates } from "@/lib/live-updates"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field"
import { useAsyncAction } from "@/hooks/use-async-action"
import { useResource } from "@/hooks/use-resource"
import {
    type FormEvent,
    useCallback,
    useEffect,
    useReducer,
    useState,
} from "react"
import { LoaderCircle, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { pageContaining } from "@/lib/utils"
import { apiErrorMessage } from "@/lib/errors"

type QuizzesPanelProps = {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
    gradeLevels: GradeLevel[]
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
}

const PAGE_SIZE = 8

function isActiveSession(session: QuizSession): boolean {
    return isActiveSessionStatus(session.status)
}

function loadSupportData() {
    return Promise.all([getAllQuestionBanks(), getAllStudentClasses()])
}

export function QuizzesPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
    gradeLevels,
    onDeleteGradeLevel,
}: QuizzesPanelProps) {
    const { t, i18n } = useTranslation()
    const [page, setPage] = useState(1)
    const [quizFilter, setQuizFilter] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
    const support = useResource(loadSupportData)
    const [banks, classes] = support.data ?? [[], []]
    const quizList = useResource(
        useCallback(
            () =>
                getQuizzes(
                    page,
                    quizFilter.trim(),
                    gradeLevelFilter,
                    PAGE_SIZE
                ),
            [gradeLevelFilter, page, quizFilter]
        )
    )
    const quizzes = quizList.data?.items ?? []
    const totalPages = quizList.data?.totalPages ?? 1
    const [sessions, setSessions] = useState<QuizSession[]>([])
    const [liveSessionsLoadFailed, setLiveSessionsLoadFailed] = useState(false)
    const [form, dispatchForm] = useReducer(quizFormReducer, emptyQuizForm)
    const [previewedQuiz, setPreviewedQuiz] = useState<Quiz | null>(null)
    const preview = useResource(
        useCallback(
            () =>
                previewedQuiz
                    ? previewQuiz(previewedQuiz.id)
                    : Promise.resolve([]),
            [previewedQuiz]
        )
    )
    const [quizToLaunch, setQuizToLaunch] = useState<Quiz | null>(null)
    const [selectedClassId, setSelectedClassId] = useState("")
    const [quizToPrint, setQuizToPrint] = useState<Quiz | null>(null)
    const [printClassId, setPrintClassId] = useState("")
    const [quizToDelete, setQuizToDelete] = useState<Quiz | null>(null)
    const [activeSession, setActiveSession] = useState<QuizSession | null>(null)
    const [activeSessionError, setActiveSessionError] = useState<string | null>(
        null
    )
    const [isStarting, setIsStarting] = useState(false)
    const [sessionAction, setSessionAction] = useState<
        "pause" | "resume" | "cancel" | "delete" | null
    >(null)
    const [sessionActionToConfirm, setSessionActionToConfirm] = useState<
        "cancel" | "delete" | null
    >(null)
    const activeSessionId = activeSession?.id

    const lastPage = quizList.data?.totalPages
    // A deletion can leave the current page past the end of the list.
    if (lastPage !== undefined && page > lastPage) setPage(lastPage)

    useEffect(
        () =>
            connectLiveUpdates<QuizSession[]>({
                path: "/api/quizzes/live/teacher/sessions",
                getToken: getLiveAccessToken,
                onData: (updatedSessions) => {
                    const activeSessions =
                        updatedSessions.filter(isActiveSession)
                    setSessions(activeSessions)
                    setActiveSession((current) => {
                        if (!current) return null
                        return (
                            activeSessions.find(
                                (session) => session.id === current.id
                            ) ?? current
                        )
                    })
                    setLiveSessionsLoadFailed(false)
                },
                onUnavailable: () => setLiveSessionsLoadFailed(true),
            }),
        []
    )

    useEffect(() => {
        if (!activeSessionId) return
        // Keep one subscription for the lifetime of the dialog. Reconnecting
        // around every Start/Pause/Resume request creates a gap exactly while
        // the backend publishes the corresponding state change.
        return connectLiveUpdates<QuizSession>({
            path: `/api/quizzes/live/teacher/sessions/${activeSessionId}`,
            getToken: getLiveAccessToken,
            onData: (session) => {
                setActiveSessionError(null)
                setActiveSession(session)
                setSessions((current) =>
                    isActiveSession(session)
                        ? current.map((item) =>
                              item.id === session.id ? session : item
                          )
                        : current.filter((item) => item.id !== session.id)
                )
            },
            onDeleted: () => {
                setSessions((current) =>
                    current.filter((item) => item.id !== activeSessionId)
                )
                setActiveSession(null)
            },
            onUnavailable: () =>
                setActiveSessionError(t("quiz-session-refresh-error")),
        })
    }, [activeSessionId, t])

    const availableByDifficulty = availableQuestionCounts(
        banks,
        form.selectedBankIds
    )
    const questionCount = Object.values(form.difficultyCounts).reduce(
        (total, count) => total + count,
        0
    )
    const loadError =
        support.error || quizList.error || liveSessionsLoadFailed
            ? t("quizzes-load-error")
            : null

    const saving = useAsyncAction(saveQuiz, (caught) =>
        apiErrorMessage(
            caught,
            t,
            t(form.editingQuiz ? "quiz-update-error" : "quiz-create-error")
        )
    )
    const launching = useAsyncAction(launchSelectedQuiz, (caught) =>
        apiErrorMessage(caught, t, t("quiz-launch-error"))
    )
    const printing = useAsyncAction(printSelectedQuiz, () =>
        t("quiz-print-error")
    )
    const deleting = useAsyncAction(deleteSelectedQuiz, (caught) =>
        apiErrorMessage(caught, t, t("quiz-delete-error"))
    )

    function resetCreationForm(): void {
        dispatchForm({ type: "reset" })
        saving.setError(null)
    }

    function openQuizEditor(quiz: Quiz): void {
        dispatchForm({ type: "edit", quiz })
        saving.setError(null)
    }

    async function printSelectedQuiz(
        event: FormEvent<HTMLFormElement>
    ): Promise<void> {
        event.preventDefault()
        if (!quizToPrint) return
        const studentClass = classes.find(
            (item) => String(item.id) === printClassId
        )
        if (!studentClass || studentClass.students.length === 0) return
        const printWindow = window.open("", "_blank")
        if (!printWindow) {
            printing.setError(t("quiz-print-popup-error"))
            return
        }
        printWindow.opener = null
        try {
            await printExamSubjects(
                quizToPrint,
                studentClass,
                printWindow,
                t,
                i18n.resolvedLanguage ?? "fr"
            )
        } catch (caught) {
            printWindow.close()
            throw caught
        }
        setQuizToPrint(null)
        setPrintClassId("")
    }

    async function saveQuiz(event: FormEvent<HTMLFormElement>): Promise<void> {
        event.preventDefault()
        if (questionCount === 0 || form.selectedBankIds.length === 0) return
        const { editingQuiz } = form
        const payload = {
            mode: "exam" as const,
            title: form.title.trim(),
            source_language:
                editingQuiz?.source_language ?? i18n.resolvedLanguage ?? "fr",
            question_bank_ids: form.selectedBankIds,
            duration_seconds: form.durationMinutes * 60,
            allow_previous_questions: form.allowPreviousQuestions,
            allow_answer_review: form.allowAnswerReview,
            allow_negative_points: form.allowNegativePoints,
            same_questions_for_all: form.sameQuestionsForAll,
            easy_question_count: form.difficultyCounts.easy,
            medium_question_count: form.difficultyCounts.medium,
            hard_question_count: form.difficultyCounts.hard,
        }
        if (editingQuiz) {
            const quiz = await updateQuiz(editingQuiz.id, payload)
            quizList.setData(
                (current) =>
                    current && {
                        ...current,
                        items: current.items.map((item) =>
                            item.id === quiz.id ? quiz : item
                        ),
                    }
            )
            onCreateDialogOpenChange(false)
            dispatchForm({ type: "reset" })
        } else {
            const quiz = await createQuiz(payload)
            onCreateDialogOpenChange(false)
            dispatchForm({ type: "reset" })
            setQuizFilter("")
            setGradeLevelFilter("")
            const allQuizzes = await getAllQuizzes().catch(() => [])
            setPage(pageContaining(allQuizzes, quiz.id, PAGE_SIZE))
        }
        quizList.reload()
    }

    function openPreview(quiz: Quiz): void {
        if (quiz === previewedQuiz) preview.reload()
        else setPreviewedQuiz(quiz)
    }

    async function launchSelectedQuiz(
        event: FormEvent<HTMLFormElement>
    ): Promise<void> {
        event.preventDefault()
        if (!quizToLaunch) return
        const session = await launchQuiz(
            quizToLaunch.id,
            Number(selectedClassId)
        )
        setSessions((current) =>
            current.some((item) => item.id === session.id)
                ? current.map((item) =>
                      item.id === session.id ? session : item
                  )
                : [session, ...current]
        )
        setQuizToLaunch(null)
        setSelectedClassId("")
        setActiveSessionError(null)
        setActiveSession(session)
    }

    async function handleStart(): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setIsStarting(true)
        try {
            const started = await startQuizSession(activeSession.id)
            setActiveSession(started)
            setSessions((current) =>
                current.map((session) =>
                    session.id === started.id ? started : session
                )
            )
        } catch (caught) {
            setActiveSessionError(
                apiErrorMessage(caught, t, t("quiz-start-error"))
            )
        } finally {
            setIsStarting(false)
        }
    }

    function updateSession(updated: QuizSession): void {
        setActiveSession(updated)
        setSessions((current) =>
            current.map((session) =>
                session.id === updated.id ? updated : session
            )
        )
    }

    async function handleSessionAction(
        action: "pause" | "resume" | "cancel"
    ): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setSessionAction(action)
        try {
            if (action === "cancel") {
                await cancelQuizSession(activeSession.id)
                setSessions((current) =>
                    current.filter((item) => item.id !== activeSession.id)
                )
                setActiveSession(null)
            } else {
                const updated =
                    action === "pause"
                        ? await pauseQuizSession(activeSession.id)
                        : await resumeQuizSession(activeSession.id)
                updateSession(updated)
            }
            setSessionActionToConfirm(null)
        } catch (caught) {
            setActiveSessionError(
                apiErrorMessage(
                    caught,
                    t,
                    caught instanceof ApiError && caught.status === 409
                        ? action === "cancel"
                            ? t("quiz-cancel-with-answers-error")
                            : t("quiz-session-action-error")
                        : t("quiz-session-action-error")
                )
            )
        } finally {
            setSessionAction(null)
        }
    }

    async function handleDeleteSession(): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setSessionAction("delete")
        try {
            await deleteQuizSession(activeSession.id)
            setSessions((current) =>
                current.filter((session) => session.id !== activeSession.id)
            )
            setSessionActionToConfirm(null)
            setActiveSession(null)
        } catch (caught) {
            setActiveSessionError(
                apiErrorMessage(caught, t, t("quiz-session-delete-error"))
            )
        } finally {
            setSessionAction(null)
        }
    }

    async function deleteSelectedQuiz(): Promise<void> {
        if (!quizToDelete) return
        await deleteQuiz(quizToDelete.id)
        setQuizToDelete(null)
        quizList.reload()
    }

    return (
        <div className="mt-6">
            <QuizzesList
                quizzes={quizzes}
                sessions={sessions}
                gradeLevels={gradeLevels}
                isLoading={!support.hasSettled || !quizList.hasSettled}
                loadError={loadError}
                quizFilter={quizFilter}
                gradeLevelFilter={gradeLevelFilter}
                onQuizFilterChange={(value) => {
                    setQuizFilter(value)
                    setPage(1)
                }}
                onGradeLevelFilterChange={(value) => {
                    setGradeLevelFilter(value)
                    setPage(1)
                }}
                onDeleteGradeLevel={onDeleteGradeLevel}
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                onEdit={openQuizEditor}
                onPreview={openPreview}
                onLaunch={(quiz) => {
                    launching.setError(null)
                    setQuizToLaunch(quiz)
                }}
                onDelete={(quiz) => {
                    deleting.setError(null)
                    setQuizToDelete(quiz)
                }}
                onPrint={(quiz) => {
                    printing.setError(null)
                    setPrintClassId("")
                    setQuizToPrint(quiz)
                }}
                onOpenSession={(quizSession) => {
                    setActiveSessionError(null)
                    setActiveSession(quizSession)
                }}
            />

            <QuizFormDialog
                open={isCreateDialogOpen || form.editingQuiz !== null}
                editingQuiz={form.editingQuiz}
                banks={banks}
                gradeLevels={gradeLevels}
                quizGradeLevel={form.gradeLevel}
                title={form.title}
                durationMinutes={form.durationMinutes}
                selectedBankIds={form.selectedBankIds}
                allowPreviousQuestions={form.allowPreviousQuestions}
                allowAnswerReview={form.allowAnswerReview}
                allowNegativePoints={form.allowNegativePoints}
                sameQuestionsForAll={form.sameQuestionsForAll}
                difficultyCounts={form.difficultyCounts}
                availableByDifficulty={availableByDifficulty}
                isBusy={saving.isPending}
                error={saving.error}
                onTitleChange={(value) =>
                    dispatchForm({ type: "set", field: "title", value })
                }
                onDurationChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "durationMinutes",
                        value,
                    })
                }
                onQuizGradeLevelChange={(gradeLevel) =>
                    dispatchForm({ type: "grade-level", gradeLevel })
                }
                onDeleteGradeLevel={onDeleteGradeLevel}
                onSelectedBankIdsChange={(ids) =>
                    dispatchForm({ type: "banks", ids, banks })
                }
                onAllowPreviousQuestionsChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "allowPreviousQuestions",
                        value,
                    })
                }
                onAllowAnswerReviewChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "allowAnswerReview",
                        value,
                    })
                }
                onAllowNegativePointsChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "allowNegativePoints",
                        value,
                    })
                }
                onSameQuestionsForAllChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "sameQuestionsForAll",
                        value,
                    })
                }
                onDifficultyCountsChange={(value) =>
                    dispatchForm({
                        type: "set",
                        field: "difficultyCounts",
                        value,
                    })
                }
                onClose={() => {
                    onCreateDialogOpenChange(false)
                    resetCreationForm()
                }}
                onSubmit={(event) => void saving.run(event)}
            />

            <QuizPreviewDialog
                quiz={previewedQuiz}
                questions={preview.isLoading ? [] : (preview.data ?? [])}
                isLoading={previewedQuiz !== null && preview.isLoading}
                error={
                    preview.error
                        ? apiErrorMessage(
                              preview.error,
                              t,
                              t("quiz-preview-error")
                          )
                        : null
                }
                onClose={() => setPreviewedQuiz(null)}
                onRefresh={openPreview}
            />

            <LaunchQuizDialog
                quiz={quizToLaunch}
                classes={classes}
                selectedClassId={selectedClassId}
                isBusy={launching.isPending}
                error={launching.error}
                onSelectedClassIdChange={setSelectedClassId}
                onClose={() => setQuizToLaunch(null)}
                onSubmit={(event) => void launching.run(event)}
            />

            <PrintQuizDialog
                quiz={quizToPrint}
                classes={classes}
                selectedClassId={printClassId}
                isBusy={printing.isPending}
                error={printing.error}
                onSelectedClassIdChange={setPrintClassId}
                onClose={() => {
                    setQuizToPrint(null)
                    setPrintClassId("")
                    printing.setError(null)
                }}
                onSubmit={(event) => void printing.run(event)}
            />

            <ActiveQuizSessionDialog
                session={activeSession}
                error={activeSessionError}
                isStarting={isStarting}
                action={sessionAction}
                onClose={() => {
                    setActiveSession(null)
                    setActiveSessionError(null)
                }}
                onStart={() => void handleStart()}
                onPause={() => void handleSessionAction("pause")}
                onResume={() => void handleSessionAction("resume")}
                onConfirmCancel={() => {
                    setActiveSessionError(null)
                    setSessionActionToConfirm("cancel")
                }}
                onConfirmDelete={() => {
                    setActiveSessionError(null)
                    setSessionActionToConfirm("delete")
                }}
            />

            <SessionActionDialog
                actionToConfirm={sessionActionToConfirm}
                currentAction={sessionAction}
                error={activeSessionError}
                onClose={() => setSessionActionToConfirm(null)}
                onConfirm={(action) =>
                    action === "delete"
                        ? void handleDeleteSession()
                        : void handleSessionAction("cancel")
                }
            />

            <Dialog
                open={quizToDelete !== null}
                onOpenChange={(open) => {
                    if (!open && !deleting.isPending) setQuizToDelete(null)
                }}
                title={t("delete-quiz")}
                description={t("delete-quiz-help", {
                    title: quizToDelete?.title ?? "",
                })}
                size="sm"
            >
                {deleting.error && (
                    <FieldError className="mb-4">{deleting.error}</FieldError>
                )}
                <div className="flex justify-end gap-2">
                    <Button
                        variant="outline"
                        disabled={deleting.isPending}
                        onClick={() => setQuizToDelete(null)}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        variant="destructive"
                        disabled={deleting.isPending}
                        onClick={() => void deleting.run()}
                    >
                        {deleting.isPending ? (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        ) : (
                            <Trash2 />
                        )}
                        {t("delete")}
                    </Button>
                </div>
            </Dialog>
        </div>
    )
}

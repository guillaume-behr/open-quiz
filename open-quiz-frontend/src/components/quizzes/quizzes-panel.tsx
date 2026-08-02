import { getAllStudentClasses } from "@/api/classes"
import { getAllQuestionBanks } from "@/api/question-banks"
import {
    cancelQuizSession,
    createQuiz,
    deleteQuiz,
    deleteQuizSession,
    getAllQuizzes,
    getActiveQuizSessions,
    getQuizSession,
    getQuizzes,
    launchQuiz,
    pauseQuizSession,
    previewQuiz,
    resumeQuizSession,
    startQuizSession,
    updateQuiz,
} from "@/api/quizzes"
import type {
    Question,
    QuestionBank,
    Quiz,
    QuizSession,
    StudentClass,
} from "@/api/types"
import { ActiveQuizSessionDialog } from "@/components/quizzes/active-quiz-session-dialog"
import { QuizFormDialog } from "@/components/quizzes/quiz-form-dialog"
import {
    LaunchQuizDialog,
    QuizPreviewDialog,
    SessionActionDialog,
} from "@/components/quizzes/quiz-secondary-dialogs"
import { QuizzesList } from "@/components/quizzes/quizzes-list"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field"
import { type FormEvent, useEffect, useRef, useState } from "react"
import { LoaderCircle, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"

type QuizzesPanelProps = {
    mode: "exam"
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
}

const difficultyKeys = ["easy", "medium", "hard"] as const
const PAGE_SIZE = 8

function pageContaining(items: Quiz[], id: number): number {
    const index = items.findIndex((item) => item.id === id)
    return index < 0 ? 1 : Math.floor(index / PAGE_SIZE) + 1
}

type Difficulty = (typeof difficultyKeys)[number]

export function QuizzesPanel({
    mode,
    isCreateDialogOpen,
    onCreateDialogOpenChange,
}: QuizzesPanelProps) {
    const { t, i18n } = useTranslation()
    const [quizzes, setQuizzes] = useState<Quiz[]>([])
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)
    const [reloadKey, setReloadKey] = useState(0)
    const [sessions, setSessions] = useState<QuizSession[]>([])
    const [banks, setBanks] = useState<QuestionBank[]>([])
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [supportLoadFailed, setSupportLoadFailed] = useState(false)
    const [quizListLoadFailed, setQuizListLoadFailed] = useState(false)
    const [title, setTitle] = useState("")
    const [selectedBankIds, setSelectedBankIds] = useState<number[]>([])
    const [durationMinutes, setDurationMinutes] = useState(30)
    const [allowPreviousQuestions, setAllowPreviousQuestions] = useState(false)
    const [difficultyCounts, setDifficultyCounts] = useState({
        easy: 0,
        medium: 0,
        hard: 0,
    })
    const [difficultyPoints, setDifficultyPoints] = useState({
        easy: 0,
        medium: 0,
        hard: 0,
    })
    const [isCreating, setIsCreating] = useState(false)
    const [createError, setCreateError] = useState<string | null>(null)
    const [editingQuiz, setEditingQuiz] = useState<Quiz | null>(null)
    const [previewedQuiz, setPreviewedQuiz] = useState<Quiz | null>(null)
    const [previewQuestions, setPreviewQuestions] = useState<Question[]>([])
    const [isPreviewLoading, setIsPreviewLoading] = useState(false)
    const [previewError, setPreviewError] = useState<string | null>(null)
    const [quizToLaunch, setQuizToLaunch] = useState<Quiz | null>(null)
    const [selectedClassId, setSelectedClassId] = useState("")
    const [isLaunching, setIsLaunching] = useState(false)
    const [launchError, setLaunchError] = useState<string | null>(null)
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
    const [quizFilter, setQuizFilter] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
    const [quizToDelete, setQuizToDelete] = useState<Quiz | null>(null)
    const [isDeleting, setIsDeleting] = useState(false)
    const [deleteError, setDeleteError] = useState<string | null>(null)
    const sessionRequestVersion = useRef(0)
    const previewRequestVersion = useRef(0)
    const activeSessionId = activeSession?.id
    const activeSessionStatus = activeSession?.status
    const isSessionMutating = isStarting || sessionAction !== null

    useEffect(() => {
        let isActive = true
        Promise.all([
            getAllQuestionBanks(),
            mode === "exam" ? getActiveQuizSessions() : Promise.resolve([]),
            getAllStudentClasses(),
        ])
            .then(([loadedBanks, loadedSessions, loadedClasses]) => {
                if (!isActive) return
                setBanks(loadedBanks)
                setSessions(loadedSessions)
                setClasses(loadedClasses)
                setSupportLoadFailed(false)
            })
            .catch(() => {
                if (isActive) setSupportLoadFailed(true)
            })
            .finally(() => {
                if (isActive) setIsLoading(false)
            })
        return () => {
            isActive = false
        }
    }, [mode, t])

    useEffect(() => {
        let isActive = true
        getQuizzes(page, quizFilter.trim(), gradeLevelFilter, 8, mode)
            .then((result) => {
                if (!isActive) return
                setQuizzes(result.items)
                setTotalPages(result.totalPages)
                setQuizListLoadFailed(false)
                if (result.page > result.totalPages) setPage(result.totalPages)
            })
            .catch(() => {
                if (isActive) setQuizListLoadFailed(true)
            })
            .finally(() => {
                if (isActive) setIsLoading(false)
            })
        return () => {
            isActive = false
        }
    }, [gradeLevelFilter, mode, page, quizFilter, reloadKey, t])

    useEffect(() => {
        if (
            !activeSessionId ||
            isSessionMutating ||
            !["waiting", "in_progress", "paused"].includes(
                activeSessionStatus ?? ""
            )
        )
            return
        let isActive = true
        let refreshInFlight = false
        const refresh = () => {
            if (refreshInFlight) return
            refreshInFlight = true
            const requestVersion = sessionRequestVersion.current
            void getQuizSession(activeSessionId)
                .then((session) => {
                    if (
                        !isActive ||
                        requestVersion !== sessionRequestVersion.current
                    )
                        return
                    setActiveSessionError(null)
                    setActiveSession(session)
                    setSessions((current) =>
                        current.map((item) =>
                            item.id === session.id ? session : item
                        )
                    )
                })
                .catch(() => {
                    if (
                        isActive &&
                        requestVersion === sessionRequestVersion.current
                    ) {
                        setActiveSessionError(t("quiz-session-refresh-error"))
                    }
                })
                .finally(() => {
                    refreshInFlight = false
                })
        }
        const interval = window.setInterval(refresh, 1500)
        return () => {
            isActive = false
            window.clearInterval(interval)
        }
    }, [activeSessionId, activeSessionStatus, isSessionMutating, t])

    const availableByDifficulty = difficultyKeys.reduce(
        (result, difficulty) => {
            result[difficulty] = banks
                .filter((bank) => selectedBankIds.includes(bank.id))
                .reduce(
                    (total, bank) =>
                        total + bank[`${difficulty}_question_count`],
                    0
                )
            return result
        },
        { easy: 0, medium: 0, hard: 0 } as Record<Difficulty, number>
    )
    const questionCount = Object.values(difficultyCounts).reduce(
        (total, count) => total + count,
        0
    )
    const quizGradeLevels = Array.from(
        new Set(banks.map((bank) => bank.grade_level))
    ).sort((first, second) => first.localeCompare(second, "fr"))
    const loadError =
        supportLoadFailed || quizListLoadFailed ? t("quizzes-load-error") : null

    function handleSelectedBankIdsChange(ids: number[]): void {
        setSelectedBankIds(ids)
        const available = difficultyKeys.reduce(
            (result, difficulty) => {
                result[difficulty] = banks
                    .filter((bank) => ids.includes(bank.id))
                    .reduce(
                        (total, bank) =>
                            total + bank[`${difficulty}_question_count`],
                        0
                    )
                return result
            },
            { easy: 0, medium: 0, hard: 0 } as Record<Difficulty, number>
        )
        setDifficultyCounts((current) => ({
            easy: Math.min(current.easy, available.easy),
            medium: Math.min(current.medium, available.medium),
            hard: Math.min(current.hard, available.hard),
        }))
        setDifficultyPoints((current) => ({
            easy: available.easy > 0 ? current.easy : 0,
            medium: available.medium > 0 ? current.medium : 0,
            hard: available.hard > 0 ? current.hard : 0,
        }))
    }

    function handleDifficultyCountsChange(
        values: Record<Difficulty, number>
    ): void {
        setDifficultyCounts(values)
        setDifficultyPoints((current) => ({
            easy: values.easy > 0 ? current.easy : 0,
            medium: values.medium > 0 ? current.medium : 0,
            hard: values.hard > 0 ? current.hard : 0,
        }))
    }

    function resetCreationForm(): void {
        setTitle("")
        setSelectedBankIds([])
        setDurationMinutes(30)
        setAllowPreviousQuestions(false)
        setDifficultyCounts({ easy: 0, medium: 0, hard: 0 })
        setDifficultyPoints({ easy: 0, medium: 0, hard: 0 })
        setCreateError(null)
        setEditingQuiz(null)
    }

    function openQuizEditor(quiz: Quiz): void {
        setEditingQuiz(quiz)
        setTitle(quiz.title)
        setSelectedBankIds(quiz.question_banks.map((bank) => bank.id))
        setDurationMinutes(quiz.duration_seconds / 60)
        setAllowPreviousQuestions(quiz.allow_previous_questions)
        setDifficultyCounts({
            easy: quiz.easy_question_count,
            medium: quiz.medium_question_count,
            hard: quiz.hard_question_count,
        })
        setDifficultyPoints({
            easy: quiz.easy_points,
            medium: quiz.medium_points,
            hard: quiz.hard_points,
        })
        setCreateError(null)
    }

    async function handleCreate(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (questionCount === 0 || selectedBankIds.length === 0) return
        setCreateError(null)
        setIsCreating(true)
        try {
            const payload = {
                mode,
                title: title.trim(),
                source_language:
                    editingQuiz?.source_language ??
                    i18n.resolvedLanguage ??
                    "fr",
                question_bank_ids: selectedBankIds,
                duration_seconds: durationMinutes * 60,
                allow_previous_questions: allowPreviousQuestions,
                same_questions_for_all: false,
                easy_question_count: difficultyCounts.easy,
                medium_question_count: difficultyCounts.medium,
                hard_question_count: difficultyCounts.hard,
                easy_points: mode === "exam" ? difficultyPoints.easy : 0,
                medium_points: mode === "exam" ? difficultyPoints.medium : 0,
                hard_points: mode === "exam" ? difficultyPoints.hard : 0,
            }
            const isEditing = editingQuiz !== null
            const quiz = isEditing
                ? await updateQuiz(editingQuiz.id, payload)
                : await createQuiz(payload)
            setQuizzes((current) =>
                editingQuiz
                    ? current.map((item) => (item.id === quiz.id ? quiz : item))
                    : [quiz, ...current]
            )
            onCreateDialogOpenChange(false)
            resetCreationForm()
            if (!isEditing) {
                setQuizFilter("")
                setGradeLevelFilter("")
                const allQuizzes = await getAllQuizzes(mode).catch(() => [])
                setPage(pageContaining(allQuizzes, quiz.id))
            }
            setReloadKey((current) => current + 1)
        } catch {
            setCreateError(
                t(editingQuiz ? "quiz-update-error" : "quiz-create-error")
            )
        } finally {
            setIsCreating(false)
        }
    }

    async function openPreview(quiz: Quiz): Promise<void> {
        const requestVersion = ++previewRequestVersion.current
        setPreviewedQuiz(quiz)
        setPreviewQuestions([])
        setPreviewError(null)
        setIsPreviewLoading(true)
        try {
            const questions = await previewQuiz(quiz.id)
            if (requestVersion === previewRequestVersion.current)
                setPreviewQuestions(questions)
        } catch {
            if (requestVersion === previewRequestVersion.current)
                setPreviewError(t("quiz-preview-error"))
        } finally {
            if (requestVersion === previewRequestVersion.current)
                setIsPreviewLoading(false)
        }
    }

    function closePreview(): void {
        previewRequestVersion.current += 1
        setPreviewedQuiz(null)
        setIsPreviewLoading(false)
    }

    async function handleLaunch(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!quizToLaunch) return
        setLaunchError(null)
        setIsLaunching(true)
        try {
            const session = await launchQuiz(
                quizToLaunch.id,
                Number(selectedClassId)
            )
            setSessions((current) => [session, ...current])
            setQuizToLaunch(null)
            setSelectedClassId("")
            setActiveSessionError(null)
            sessionRequestVersion.current += 1
            setActiveSession(session)
        } catch {
            setLaunchError(t("quiz-launch-error"))
        } finally {
            setIsLaunching(false)
        }
    }

    async function handleStart(): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setIsStarting(true)
        sessionRequestVersion.current += 1
        try {
            const started = await startQuizSession(activeSession.id)
            setActiveSession(started)
            setSessions((current) =>
                current.map((session) =>
                    session.id === started.id ? started : session
                )
            )
        } catch {
            setActiveSessionError(t("quiz-start-error"))
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
        sessionRequestVersion.current += 1
        try {
            const updated =
                action === "pause"
                    ? await pauseQuizSession(activeSession.id)
                    : action === "resume"
                      ? await resumeQuizSession(activeSession.id)
                      : await cancelQuizSession(activeSession.id)
            updateSession(updated)
            setSessionActionToConfirm(null)
        } catch {
            setActiveSessionError(t("quiz-session-action-error"))
        } finally {
            setSessionAction(null)
        }
    }

    async function handleDeleteSession(): Promise<void> {
        if (!activeSession) return
        setActiveSessionError(null)
        setSessionAction("delete")
        sessionRequestVersion.current += 1
        try {
            await deleteQuizSession(activeSession.id)
            setSessions((current) =>
                current.filter((session) => session.id !== activeSession.id)
            )
            setSessionActionToConfirm(null)
            setActiveSession(null)
        } catch {
            setActiveSessionError(t("quiz-session-delete-error"))
        } finally {
            setSessionAction(null)
        }
    }

    async function handleDeleteQuiz(): Promise<void> {
        if (!quizToDelete) return
        setDeleteError(null)
        setIsDeleting(true)
        try {
            await deleteQuiz(quizToDelete.id)
            setQuizToDelete(null)
            setReloadKey((k) => k + 1)
        } catch {
            setDeleteError(t("quiz-delete-error"))
        } finally {
            setIsDeleting(false)
        }
    }

    return (
        <div className="mt-6">
            <QuizzesList
                mode={mode}
                quizzes={quizzes}
                filteredQuizzes={quizzes}
                sessions={sessions}
                gradeLevels={quizGradeLevels}
                isLoading={isLoading}
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
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
                onEdit={openQuizEditor}
                onPreview={(quiz) => void openPreview(quiz)}
                onLaunch={(quiz) => {
                    setLaunchError(null)
                    setQuizToLaunch(quiz)
                }}
                onDelete={(quiz) => {
                    setDeleteError(null)
                    setQuizToDelete(quiz)
                }}
                onOpenSession={(quizSession) => {
                    setActiveSessionError(null)
                    setActiveSession(quizSession)
                }}
            />

            <QuizFormDialog
                mode={mode}
                open={isCreateDialogOpen || editingQuiz !== null}
                editingQuiz={editingQuiz}
                banks={banks}
                title={title}
                durationMinutes={durationMinutes}
                selectedBankIds={selectedBankIds}
                allowPreviousQuestions={allowPreviousQuestions}
                difficultyCounts={difficultyCounts}
                difficultyPoints={difficultyPoints}
                availableByDifficulty={availableByDifficulty}
                isBusy={isCreating}
                error={createError}
                onTitleChange={setTitle}
                onDurationChange={setDurationMinutes}
                onSelectedBankIdsChange={handleSelectedBankIdsChange}
                onAllowPreviousQuestionsChange={setAllowPreviousQuestions}
                onDifficultyCountsChange={handleDifficultyCountsChange}
                onDifficultyPointsChange={setDifficultyPoints}
                onClose={() => {
                    onCreateDialogOpenChange(false)
                    resetCreationForm()
                }}
                onSubmit={handleCreate}
            />

            <QuizPreviewDialog
                quiz={previewedQuiz}
                questions={previewQuestions}
                isLoading={isPreviewLoading}
                error={previewError}
                onClose={closePreview}
                onRefresh={(quiz) => void openPreview(quiz)}
            />

            <LaunchQuizDialog
                quiz={quizToLaunch}
                classes={classes}
                selectedClassId={selectedClassId}
                isBusy={isLaunching}
                error={launchError}
                onSelectedClassIdChange={setSelectedClassId}
                onClose={() => setQuizToLaunch(null)}
                onSubmit={handleLaunch}
            />

            <ActiveQuizSessionDialog
                session={activeSession}
                error={activeSessionError}
                isStarting={isStarting}
                action={sessionAction}
                onClose={() => {
                    sessionRequestVersion.current += 1
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
                    if (!open && !isDeleting) setQuizToDelete(null)
                }}
                title={t("delete-quiz")}
                description={t("delete-quiz-help", {
                    title: quizToDelete?.title ?? "",
                })}
                className="max-w-md"
            >
                {deleteError && (
                    <FieldError className="mb-4">{deleteError}</FieldError>
                )}
                <div className="flex justify-end gap-2">
                    <Button
                        variant="outline"
                        disabled={isDeleting}
                        onClick={() => setQuizToDelete(null)}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        variant="destructive"
                        disabled={isDeleting}
                        onClick={() => void handleDeleteQuiz()}
                    >
                        {isDeleting ? (
                            <LoaderCircle className="animate-spin" />
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

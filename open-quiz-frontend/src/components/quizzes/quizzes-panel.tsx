import { getAllStudentClasses } from "@/api/classes"
import { getAllQuestionBanks } from "@/api/question-banks"
import {
    cancelQuizSession,
    createQuiz,
    deleteQuizSession,
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
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

type QuizzesPanelProps = {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
}

const difficultyKeys = ["easy", "medium", "hard"] as const
type Difficulty = (typeof difficultyKeys)[number]
const easePriority: Record<Difficulty, number> = {
    easy: 2,
    medium: 1,
    hard: 0,
}
function calculateDifficultyCounts(
    questionCount: number,
    percentages: Record<Difficulty, number>,
    available: Record<Difficulty, number>
): Record<Difficulty, number> {
    const exact = Object.fromEntries(
        difficultyKeys.map((difficulty) => [
            difficulty,
            (questionCount * percentages[difficulty]) / 100,
        ])
    ) as Record<Difficulty, number>
    let counts = Object.fromEntries(
        difficultyKeys.map((difficulty) => [
            difficulty,
            Math.floor(exact[difficulty]),
        ])
    ) as Record<Difficulty, number>
    let remaining =
        questionCount - Object.values(counts).reduce((a, b) => a + b)
    const roundingOrder = [...difficultyKeys].sort(
        (first, second) =>
            exact[second] - counts[second] - (exact[first] - counts[first]) ||
            percentages[second] - percentages[first] ||
            easePriority[second] - easePriority[first]
    )
    for (const difficulty of roundingOrder.slice(0, remaining)) {
        counts[difficulty] += 1
    }
    counts = Object.fromEntries(
        difficultyKeys.map((difficulty) => [
            difficulty,
            Math.min(counts[difficulty], available[difficulty]),
        ])
    ) as Record<Difficulty, number>
    remaining = questionCount - Object.values(counts).reduce((a, b) => a + b)
    while (remaining > 0) {
        const candidates = difficultyKeys.filter(
            (difficulty) => counts[difficulty] < available[difficulty]
        )
        if (candidates.length === 0) break
        const difficulty = candidates.sort(
            (first, second) =>
                percentages[second] - percentages[first] ||
                easePriority[second] - easePriority[first]
        )[0]
        counts[difficulty] += 1
        remaining -= 1
    }
    return counts
}

export function QuizzesPanel({
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
    const [questionCount, setQuestionCount] = useState(10)
    const [durationMinutes, setDurationMinutes] = useState(30)
    const [allowPreviousQuestions, setAllowPreviousQuestions] = useState(false)
    const [percentages, setPercentages] = useState({
        easy: 30,
        medium: 40,
        hard: 30,
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
    const activeSessionId = activeSession?.id
    const activeSessionStatus = activeSession?.status

    useEffect(() => {
        let isActive = true
        Promise.all([
            getAllQuestionBanks(),
            getActiveQuizSessions(),
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
    }, [t])

    useEffect(() => {
        let isActive = true
        getQuizzes(page, quizFilter.trim(), gradeLevelFilter)
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
    }, [gradeLevelFilter, page, quizFilter, reloadKey, t])

    useEffect(() => {
        if (
            !activeSessionId ||
            !["waiting", "in_progress", "paused"].includes(
                activeSessionStatus ?? ""
            )
        )
            return
        let isActive = true
        const refresh = () => {
            void getQuizSession(activeSessionId)
                .then((session) => {
                    if (!isActive) return
                    setActiveSessionError(null)
                    setActiveSession(session)
                    setSessions((current) =>
                        current.map((item) =>
                            item.id === session.id ? session : item
                        )
                    )
                })
                .catch(() => {
                    if (isActive) {
                        setActiveSessionError(t("quiz-session-refresh-error"))
                    }
                })
        }
        const interval = window.setInterval(refresh, 1500)
        return () => {
            isActive = false
            window.clearInterval(interval)
        }
    }, [activeSessionId, activeSessionStatus, t])

    const percentageTotal =
        percentages.easy + percentages.medium + percentages.hard
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
    const difficultyPreview =
        percentageTotal === 100
            ? calculateDifficultyCounts(
                  questionCount,
                  percentages,
                  availableByDifficulty
              )
            : { easy: 0, medium: 0, hard: 0 }
    const previewQuestionTotal = Object.values(difficultyPreview).reduce(
        (total, count) => total + count,
        0
    )
    const quizGradeLevels = Array.from(
        new Set(banks.map((bank) => bank.grade_level))
    ).sort((first, second) => first.localeCompare(second, "fr"))
    const filteredQuizzes = quizzes
    const loadError =
        supportLoadFailed || quizListLoadFailed ? t("quizzes-load-error") : null

    function resetCreationForm(): void {
        setTitle("")
        setSelectedBankIds([])
        setQuestionCount(10)
        setDurationMinutes(30)
        setAllowPreviousQuestions(false)
        setPercentages({ easy: 30, medium: 40, hard: 30 })
        setCreateError(null)
        setEditingQuiz(null)
    }

    function openQuizEditor(quiz: Quiz): void {
        setEditingQuiz(quiz)
        setTitle(quiz.title)
        setSelectedBankIds(quiz.question_banks.map((bank) => bank.id))
        setQuestionCount(quiz.question_count)
        setDurationMinutes(quiz.duration_seconds / 60)
        setAllowPreviousQuestions(quiz.allow_previous_questions)
        setPercentages({
            easy: quiz.easy_percentage,
            medium: quiz.medium_percentage,
            hard: quiz.hard_percentage,
        })
        setCreateError(null)
    }

    async function handleCreate(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (percentageTotal !== 100 || selectedBankIds.length === 0) return
        setCreateError(null)
        setIsCreating(true)
        try {
            const payload = {
                title: title.trim(),
                source_language:
                    editingQuiz?.source_language ??
                    i18n.resolvedLanguage ??
                    "fr",
                question_bank_ids: selectedBankIds,
                question_count: questionCount,
                duration_seconds: durationMinutes * 60,
                allow_previous_questions: allowPreviousQuestions,
                easy_percentage: percentages.easy,
                medium_percentage: percentages.medium,
                hard_percentage: percentages.hard,
            }
            const quiz = editingQuiz
                ? await updateQuiz(editingQuiz.id, payload)
                : await createQuiz(payload)
            setQuizzes((current) =>
                editingQuiz
                    ? current.map((item) => (item.id === quiz.id ? quiz : item))
                    : [quiz, ...current]
            )
            onCreateDialogOpenChange(false)
            resetCreationForm()
            setPage(1)
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
        setPreviewedQuiz(quiz)
        setPreviewQuestions([])
        setPreviewError(null)
        setIsPreviewLoading(true)
        try {
            setPreviewQuestions(await previewQuiz(quiz.id))
        } catch {
            setPreviewError(t("quiz-preview-error"))
        } finally {
            setIsPreviewLoading(false)
        }
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

    return (
        <div className="mt-6">
            <QuizzesList
                quizzes={quizzes}
                filteredQuizzes={filteredQuizzes}
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
                onOpenSession={(quizSession) => {
                    setActiveSessionError(null)
                    setActiveSession(quizSession)
                }}
            />

            <QuizFormDialog
                open={isCreateDialogOpen || editingQuiz !== null}
                editingQuiz={editingQuiz}
                banks={banks}
                title={title}
                durationMinutes={durationMinutes}
                selectedBankIds={selectedBankIds}
                allowPreviousQuestions={allowPreviousQuestions}
                questionCount={questionCount}
                percentages={percentages}
                difficultyPreview={difficultyPreview}
                availableByDifficulty={availableByDifficulty}
                previewQuestionTotal={previewQuestionTotal}
                isBusy={isCreating}
                error={createError}
                onTitleChange={setTitle}
                onDurationChange={setDurationMinutes}
                onSelectedBankIdsChange={setSelectedBankIds}
                onAllowPreviousQuestionsChange={setAllowPreviousQuestions}
                onQuestionCountChange={setQuestionCount}
                onPercentagesChange={setPercentages}
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
                onClose={() => setPreviewedQuiz(null)}
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
        </div>
    )
}

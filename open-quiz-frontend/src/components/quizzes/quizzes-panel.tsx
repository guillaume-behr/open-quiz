import {
    createQuiz,
    getActiveQuizSessions,
    getQuestionBanks,
    getQuizSession,
    getQuizzes,
    getStudentClasses,
    launchQuiz,
    previewQuiz,
    startQuizSession,
    type Question,
    type QuestionBank,
    type Quiz,
    type QuizSession,
    type StudentClass,
} from "@/api/api"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { QuizTimer } from "@/components/quizzes/quiz-timer"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
    BookOpenText,
    AlertTriangle,
    Eye,
    LoaderCircle,
    Play,
    Plus,
    RefreshCw,
    UsersRound,
} from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

type QuizzesPanelProps = {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
}

const difficultyKeys = ["easy", "medium", "hard"] as const

export function QuizzesPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
}: QuizzesPanelProps) {
    const { t } = useTranslation()
    const [quizzes, setQuizzes] = useState<Quiz[]>([])
    const [sessions, setSessions] = useState<QuizSession[]>([])
    const [banks, setBanks] = useState<QuestionBank[]>([])
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [loadError, setLoadError] = useState<string | null>(null)
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
    const [previewedQuiz, setPreviewedQuiz] = useState<Quiz | null>(null)
    const [previewQuestions, setPreviewQuestions] = useState<Question[]>([])
    const [isPreviewLoading, setIsPreviewLoading] = useState(false)
    const [previewError, setPreviewError] = useState<string | null>(null)
    const [quizToLaunch, setQuizToLaunch] = useState<Quiz | null>(null)
    const [selectedClassId, setSelectedClassId] = useState("")
    const [isLaunching, setIsLaunching] = useState(false)
    const [launchError, setLaunchError] = useState<string | null>(null)
    const [activeSession, setActiveSession] = useState<QuizSession | null>(null)
    const [isStarting, setIsStarting] = useState(false)
    const activeSessionId = activeSession?.id
    const activeSessionStatus = activeSession?.status

    useEffect(() => {
        let isActive = true
        Promise.all([
            getQuizzes(),
            getQuestionBanks(),
            getActiveQuizSessions(),
            getStudentClasses(),
        ])
            .then(
                ([
                    loadedQuizzes,
                    loadedBanks,
                    loadedSessions,
                    loadedClasses,
                ]) => {
                    if (!isActive) return
                    setQuizzes(loadedQuizzes)
                    setBanks(loadedBanks)
                    setSessions(loadedSessions)
                    setClasses(loadedClasses)
                }
            )
            .catch(() => {
                if (isActive) setLoadError(t("quizzes-load-error"))
            })
            .finally(() => {
                if (isActive) setIsLoading(false)
            })
        return () => {
            isActive = false
        }
    }, [t])

    useEffect(() => {
        if (
            !activeSessionId ||
            !["waiting", "in_progress"].includes(activeSessionStatus ?? "")
        )
            return
        let isActive = true
        const refresh = () => {
            void getQuizSession(activeSessionId)
                .then((session) => {
                    if (!isActive) return
                    setActiveSession(session)
                    setSessions((current) =>
                        current.map((item) =>
                            item.id === session.id ? session : item
                        )
                    )
                })
                .catch(() => undefined)
        }
        const interval = window.setInterval(refresh, 1500)
        return () => {
            isActive = false
            window.clearInterval(interval)
        }
    }, [activeSessionId, activeSessionStatus])

    const percentageTotal =
        percentages.easy + percentages.medium + percentages.hard

    function resetCreationForm(): void {
        setTitle("")
        setSelectedBankIds([])
        setQuestionCount(10)
        setDurationMinutes(30)
        setAllowPreviousQuestions(false)
        setPercentages({ easy: 30, medium: 40, hard: 30 })
        setCreateError(null)
    }

    async function handleCreate(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (percentageTotal !== 100 || selectedBankIds.length === 0) return
        setCreateError(null)
        setIsCreating(true)
        try {
            const quiz = await createQuiz({
                title: title.trim(),
                question_bank_ids: selectedBankIds,
                question_count: questionCount,
                duration_seconds: durationMinutes * 60,
                allow_previous_questions: allowPreviousQuestions,
                easy_percentage: percentages.easy,
                medium_percentage: percentages.medium,
                hard_percentage: percentages.hard,
            })
            setQuizzes((current) => [quiz, ...current])
            onCreateDialogOpenChange(false)
            resetCreationForm()
        } catch {
            setCreateError(t("quiz-create-error"))
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
            setActiveSession(session)
        } catch {
            setLaunchError(t("quiz-launch-error"))
        } finally {
            setIsLaunching(false)
        }
    }

    async function handleStart(): Promise<void> {
        if (!activeSession) return
        setIsStarting(true)
        try {
            const started = await startQuizSession(activeSession.id)
            setActiveSession(started)
            setSessions((current) =>
                current.map((session) =>
                    session.id === started.id ? started : session
                )
            )
        } finally {
            setIsStarting(false)
        }
    }

    return (
        <div className="mt-6">
            {sessions.length > 0 && (
                <div className="mb-5 rounded-xl border bg-primary/5 p-4">
                    <h3 className="font-semibold">{t("recent-sessions")}</h3>
                    <div className="mt-3 flex flex-wrap gap-2">
                        {sessions.slice(0, 6).map((session) => (
                            <Button
                                key={session.id}
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={() => setActiveSession(session)}
                            >
                                <UsersRound />
                                {session.quiz_title} · {session.class_name} ·{" "}
                                {session.participant_count}
                            </Button>
                        ))}
                    </div>
                </div>
            )}
            {isLoading ? (
                <div className="flex min-h-40 items-center justify-center">
                    <LoaderCircle className="size-7 animate-spin text-primary" />
                </div>
            ) : loadError ? (
                <p
                    role="alert"
                    className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
                >
                    {loadError}
                </p>
            ) : quizzes.length === 0 ? (
                <div className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                    <BookOpenText className="mb-2 size-8" />
                    <p className="font-medium">{t("no-quiz")}</p>
                    <p className="mt-1 text-sm">{t("no-quiz-help")}</p>
                </div>
            ) : (
                <ul className="grid gap-4 xl:grid-cols-2">
                    {quizzes.map((quiz) => (
                        <li
                            key={quiz.id}
                            className="rounded-xl border bg-background p-4"
                        >
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <h3 className="font-semibold">
                                        {quiz.title}
                                    </h3>
                                    <p className="mt-1 text-sm text-muted-foreground">
                                        {t("quiz-summary", {
                                            questions: quiz.question_count,
                                            banks: quiz.question_banks.length,
                                        })}
                                    </p>
                                </div>
                                <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold text-primary">
                                    {quiz.question_count}
                                </span>
                            </div>
                            <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-muted">
                                <span
                                    className="bg-emerald-500"
                                    style={{
                                        width: `${quiz.easy_percentage}%`,
                                    }}
                                />
                                <span
                                    className="bg-amber-500"
                                    style={{
                                        width: `${quiz.medium_percentage}%`,
                                    }}
                                />
                                <span
                                    className="bg-rose-500"
                                    style={{
                                        width: `${quiz.hard_percentage}%`,
                                    }}
                                />
                            </div>
                            <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                                {difficultyKeys.map((difficulty) => (
                                    <span key={difficulty}>
                                        {t(`difficulty-${difficulty}`)}{" "}
                                        {quiz[`${difficulty}_percentage`]} %
                                    </span>
                                ))}
                            </div>
                            <p className="mt-3 text-xs text-muted-foreground">
                                {quiz.question_banks
                                    .map(
                                        (bank) =>
                                            `${bank.grade_level} — ${bank.chapter}`
                                    )
                                    .join(" · ")}
                            </p>
                            <div className="mt-4 flex flex-wrap gap-2">
                                <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    onClick={() => void openPreview(quiz)}
                                >
                                    <Eye />
                                    {t("preview-quiz")}
                                </Button>
                                <Button
                                    type="button"
                                    size="sm"
                                    onClick={() => {
                                        setLaunchError(null)
                                        setQuizToLaunch(quiz)
                                    }}
                                >
                                    <Play />
                                    {t("launch-quiz")}
                                </Button>
                            </div>
                        </li>
                    ))}
                </ul>
            )}

            <Dialog
                open={isCreateDialogOpen}
                onOpenChange={(open) => {
                    if (isCreating) return
                    onCreateDialogOpenChange(open)
                    if (!open) resetCreationForm()
                }}
                title={t("create-quiz")}
                description={t("create-quiz-help")}
            >
                <form onSubmit={handleCreate}>
                    <FieldGroup className="gap-5">
                        <Field>
                            <FieldLabel htmlFor="quiz-title">
                                {t("quiz-title")}
                            </FieldLabel>
                            <Input
                                id="quiz-title"
                                value={title}
                                onChange={(event) =>
                                    setTitle(event.target.value)
                                }
                                maxLength={160}
                                required
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="quiz-duration">
                                {t("quiz-duration")}
                            </FieldLabel>
                            <Input
                                id="quiz-duration"
                                type="number"
                                min={1}
                                max={480}
                                value={durationMinutes}
                                onChange={(event) =>
                                    setDurationMinutes(
                                        Math.min(
                                            480,
                                            Math.max(
                                                1,
                                                Number(event.target.value)
                                            )
                                        )
                                    )
                                }
                                required
                            />
                            <p className="text-xs text-muted-foreground">
                                {t("quiz-duration-help")}
                            </p>
                        </Field>
                        <Field>
                            <FieldLabel>{t("quiz-question-banks")}</FieldLabel>
                            {banks.length === 0 ? (
                                <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                                    {t("quiz-needs-question-bank")}
                                </p>
                            ) : (
                                <div className="grid gap-2 sm:grid-cols-2">
                                    {banks.map((bank) => {
                                        const selected =
                                            selectedBankIds.includes(bank.id)
                                        return (
                                            <label
                                                key={bank.id}
                                                className={`flex cursor-pointer gap-3 rounded-lg border p-3 ${
                                                    selected
                                                        ? "border-primary bg-primary/5"
                                                        : ""
                                                }`}
                                            >
                                                <input
                                                    type="checkbox"
                                                    checked={selected}
                                                    onChange={() =>
                                                        setSelectedBankIds(
                                                            (current) =>
                                                                selected
                                                                    ? current.filter(
                                                                          (
                                                                              id
                                                                          ) =>
                                                                              id !==
                                                                              bank.id
                                                                      )
                                                                    : [
                                                                          ...current,
                                                                          bank.id,
                                                                      ]
                                                        )
                                                    }
                                                />
                                                <span className="min-w-0">
                                                    <span className="block font-medium">
                                                        {bank.chapter}
                                                    </span>
                                                    <span className="text-xs text-muted-foreground">
                                                        {bank.grade_level} ·{" "}
                                                        {t("question-count", {
                                                            count: bank.question_count,
                                                        })}
                                                    </span>
                                                </span>
                                            </label>
                                        )
                                    })}
                                </div>
                            )}
                        </Field>
                        <Field>
                            <label className="flex cursor-pointer items-start gap-3 rounded-lg border p-4">
                                <input
                                    type="checkbox"
                                    checked={allowPreviousQuestions}
                                    onChange={(event) =>
                                        setAllowPreviousQuestions(
                                            event.target.checked
                                        )
                                    }
                                />
                                <span>
                                    <span className="block font-medium">
                                        {t("allow-previous-questions")}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                        {t("allow-previous-questions-help")}
                                    </span>
                                </span>
                            </label>
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="quiz-question-count">
                                {t("quiz-question-count")}
                            </FieldLabel>
                            <Input
                                id="quiz-question-count"
                                type="number"
                                min={1}
                                max={200}
                                value={questionCount}
                                onChange={(event) =>
                                    setQuestionCount(
                                        Math.max(1, Number(event.target.value))
                                    )
                                }
                                required
                            />
                        </Field>
                        <Field>
                            <div className="flex items-center justify-between gap-3">
                                <FieldLabel>
                                    {t("difficulty-distribution")}
                                </FieldLabel>
                                <span
                                    className={`text-sm font-semibold ${
                                        percentageTotal === 100
                                            ? "text-primary"
                                            : "text-destructive"
                                    }`}
                                >
                                    {percentageTotal} %
                                </span>
                            </div>
                            <div className="mt-2 grid gap-3 sm:grid-cols-3">
                                {difficultyKeys.map((difficulty) => (
                                    <div key={difficulty}>
                                        <FieldLabel
                                            htmlFor={`quiz-${difficulty}`}
                                        >
                                            {t(`difficulty-${difficulty}`)}
                                        </FieldLabel>
                                        <Input
                                            id={`quiz-${difficulty}`}
                                            type="number"
                                            min={0}
                                            max={100}
                                            value={percentages[difficulty]}
                                            onChange={(event) =>
                                                setPercentages((current) => ({
                                                    ...current,
                                                    [difficulty]: Math.min(
                                                        100,
                                                        Math.max(
                                                            0,
                                                            Number(
                                                                event.target
                                                                    .value
                                                            )
                                                        )
                                                    ),
                                                }))
                                            }
                                            required
                                        />
                                    </div>
                                ))}
                            </div>
                            {percentageTotal !== 100 && (
                                <FieldError>
                                    {t("difficulty-total-error")}
                                </FieldError>
                            )}
                        </Field>
                        {createError && <FieldError>{createError}</FieldError>}
                        <div className="flex justify-end gap-2 border-t pt-4">
                            <Button
                                type="button"
                                variant="outline"
                                disabled={isCreating}
                                onClick={() => onCreateDialogOpenChange(false)}
                            >
                                {t("cancel")}
                            </Button>
                            <Button
                                type="submit"
                                disabled={
                                    isCreating ||
                                    percentageTotal !== 100 ||
                                    selectedBankIds.length === 0
                                }
                            >
                                {isCreating ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <Plus />
                                )}
                                {t("create-quiz")}
                            </Button>
                        </div>
                    </FieldGroup>
                </form>
            </Dialog>

            <Dialog
                open={previewedQuiz !== null}
                onOpenChange={(open) => {
                    if (!open) setPreviewedQuiz(null)
                }}
                title={previewedQuiz?.title ?? t("preview-quiz")}
                description={t("quiz-random-preview-help")}
            >
                <div className="flex justify-end">
                    <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={isPreviewLoading || !previewedQuiz}
                        onClick={() => {
                            if (previewedQuiz) void openPreview(previewedQuiz)
                        }}
                    >
                        <RefreshCw />
                        {t("draw-again")}
                    </Button>
                </div>
                {isPreviewLoading ? (
                    <div className="flex min-h-40 items-center justify-center">
                        <LoaderCircle className="size-7 animate-spin text-primary" />
                    </div>
                ) : previewError ? (
                    <FieldError>{previewError}</FieldError>
                ) : (
                    <ol className="mt-4 space-y-3">
                        {previewQuestions.map((question, index) => (
                            <li
                                key={question.id}
                                className="rounded-xl border p-4"
                            >
                                <div className="flex items-start justify-between gap-3">
                                    <p className="font-semibold">
                                        {index + 1}. {question.prompt}
                                    </p>
                                    <span className="rounded-full bg-muted px-2 py-1 text-xs">
                                        {t(`difficulty-${question.difficulty}`)}
                                    </span>
                                </div>
                                <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                                    {question.choices.map((choice) => (
                                        <li
                                            key={choice.id}
                                            className="rounded-lg bg-muted/60 px-3 py-2 text-sm"
                                        >
                                            {choice.is_correct ? "✓ " : "○ "}
                                            {choice.label}
                                        </li>
                                    ))}
                                </ul>
                            </li>
                        ))}
                    </ol>
                )}
            </Dialog>

            <Dialog
                open={quizToLaunch !== null}
                onOpenChange={(open) => {
                    if (!open && !isLaunching) setQuizToLaunch(null)
                }}
                title={t("launch-quiz")}
                description={quizToLaunch?.title}
                className="max-w-lg"
            >
                <form onSubmit={handleLaunch}>
                    <FieldGroup>
                        <Field>
                            <FieldLabel htmlFor="quiz-class-name">
                                {t("class-name")}
                            </FieldLabel>
                            <select
                                id="quiz-class-name"
                                className="h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                                value={selectedClassId}
                                onChange={(event) =>
                                    setSelectedClassId(event.target.value)
                                }
                                required
                            >
                                <option value="" disabled>
                                    {t("choose-class")}
                                </option>
                                {classes.map((studentClass) => (
                                    <option
                                        key={studentClass.id}
                                        value={studentClass.id}
                                    >
                                        {studentClass.grade_level} —{" "}
                                        {studentClass.name} (
                                        {studentClass.student_count})
                                    </option>
                                ))}
                            </select>
                            {classes.length === 0 && (
                                <FieldError>{t("quiz-needs-class")}</FieldError>
                            )}
                        </Field>
                        {launchError && <FieldError>{launchError}</FieldError>}
                        <div className="flex justify-end gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                disabled={isLaunching}
                                onClick={() => setQuizToLaunch(null)}
                            >
                                {t("cancel")}
                            </Button>
                            <Button
                                type="submit"
                                disabled={isLaunching || !selectedClassId}
                            >
                                {isLaunching ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <Play />
                                )}
                                {t("open-waiting-room")}
                            </Button>
                        </div>
                    </FieldGroup>
                </form>
            </Dialog>

            <Dialog
                open={activeSession !== null}
                onOpenChange={(open) => {
                    if (!open) setActiveSession(null)
                }}
                title={activeSession?.quiz_title ?? t("quiz-waiting-room")}
                description={
                    activeSession
                        ? `${activeSession.class_name} — ${t(
                              activeSession.status === "waiting"
                                  ? "waiting-for-students"
                                  : "quiz-started"
                          )}`
                        : undefined
                }
            >
                {activeSession && (
                    <div>
                        <div className="rounded-xl bg-primary/10 p-5 text-center">
                            <p className="text-sm text-muted-foreground">
                                {t("quiz-join-code")}
                            </p>
                            <p className="mt-1 text-4xl font-black tracking-[0.2em] text-primary">
                                {activeSession.join_code}
                            </p>
                            {activeSession.status === "in_progress" && (
                                <div className="mt-3">
                                    <QuizTimer endsAt={activeSession.ends_at} />
                                </div>
                            )}
                        </div>
                        <div className="mt-5 flex items-center justify-between gap-3">
                            <h4 className="flex items-center gap-2 font-semibold">
                                <UsersRound className="size-5" />
                                {t("joined-students", {
                                    count: activeSession.participant_count,
                                })}
                            </h4>
                            {activeSession.status === "waiting" && (
                                <span className="flex items-center gap-2 text-xs text-muted-foreground">
                                    <span className="size-2 animate-pulse rounded-full bg-emerald-500" />
                                    {t("live-updates")}
                                </span>
                            )}
                        </div>
                        {activeSession.participants.length === 0 ? (
                            <p className="mt-3 rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
                                {t("no-student-joined")}
                            </p>
                        ) : (
                            <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                                {activeSession.participants.map(
                                    (participant) => (
                                        <li
                                            key={participant.id}
                                            className="rounded-lg border bg-background px-3 py-2 font-medium"
                                        >
                                            <span className="block">
                                                {participant.student_display_name ??
                                                    participant.student_identifier}
                                            </span>
                                            {participant.student_display_name && (
                                                <span className="block text-xs font-normal text-muted-foreground">
                                                    {
                                                        participant.student_identifier
                                                    }
                                                </span>
                                            )}
                                            {activeSession.status ===
                                                "finished" && (
                                                <span className="block text-sm font-semibold text-primary">
                                                    {t(
                                                        "teacher-student-result",
                                                        {
                                                            score: participant.score,
                                                            count: participant.answered_count,
                                                            total: activeSession.total_questions,
                                                        }
                                                    )}
                                                </span>
                                            )}
                                            {activeSession.status ===
                                                "in_progress" && (
                                                <span className="block text-sm font-semibold text-primary">
                                                    {t(
                                                        "teacher-student-progress",
                                                        {
                                                            count: participant.answered_count,
                                                            total: activeSession.total_questions,
                                                        }
                                                    )}
                                                </span>
                                            )}
                                            {participant.violation_count >
                                                0 && (
                                                <span className="mt-1 flex items-center gap-1 text-xs font-semibold text-destructive">
                                                    <AlertTriangle className="size-3" />
                                                    {t(
                                                        "student-monitoring-alert",
                                                        {
                                                            count: participant.violation_count,
                                                            event: t(
                                                                `violation-${participant.last_violation_type}`
                                                            ),
                                                        }
                                                    )}
                                                </span>
                                            )}
                                        </li>
                                    )
                                )}
                            </ul>
                        )}
                        {activeSession.status === "waiting" && (
                            <div className="mt-5 flex justify-end border-t pt-4">
                                <Button
                                    type="button"
                                    size="lg"
                                    disabled={
                                        isStarting ||
                                        activeSession.participant_count === 0
                                    }
                                    onClick={() => void handleStart()}
                                >
                                    {isStarting ? (
                                        <LoaderCircle className="animate-spin" />
                                    ) : (
                                        <Play />
                                    )}
                                    {t("start-quiz")}
                                </Button>
                            </div>
                        )}
                    </div>
                )}
            </Dialog>
        </div>
    )
}

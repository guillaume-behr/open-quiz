import type { GradeLevel, Quiz, QuizSession } from "@/api/types"
import { GradeLevelSelect } from "@/components/grade-level-select"
import { isActiveSessionStatus } from "@/lib/session-status"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Pagination } from "@/components/ui/pagination"
import {
    BookOpenText,
    Eye,
    Pencil,
    Play,
    Printer,
    Trash2,
    UsersRound,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { difficultyKeys } from "./quiz-form-state"
import { LoadingState } from "@/components/ui/loading-state"
import { AnimatedGrid } from "@/components/ui/animated-grid"
import { FilterSidebar } from "@/components/ui/filter-sidebar"

type QuizzesListProps = {
    quizzes: Quiz[]
    sessions: QuizSession[]
    gradeLevels: GradeLevel[]
    isLoading: boolean
    loadError: string | null
    quizFilter: string
    gradeLevelFilter: string
    onQuizFilterChange: (value: string) => void
    onGradeLevelFilterChange: (value: string) => void
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    onEdit: (quiz: Quiz) => void
    onPreview: (quiz: Quiz) => void
    onLaunch: (quiz: Quiz) => void
    onDelete: (quiz: Quiz) => void
    onPrint: (quiz: Quiz) => void
    onOpenSession: (session: QuizSession) => void
    page: number
    totalPages: number
    onPageChange: (page: number) => void
}

export function QuizzesList({
    quizzes,
    sessions,
    gradeLevels,
    isLoading,
    loadError,
    quizFilter,
    gradeLevelFilter,
    onQuizFilterChange,
    onGradeLevelFilterChange,
    onDeleteGradeLevel,
    onEdit,
    onPreview,
    onLaunch,
    onDelete,
    onPrint,
    onOpenSession,
    page,
    totalPages,
    onPageChange,
}: QuizzesListProps) {
    const { t } = useTranslation()
    // The API orders quizzes by title across all pages: sorting one page
    // here again would make the order differ from one page to the next.
    const activeSessions = sessions.filter((session) =>
        isActiveSessionStatus(session.status)
    )

    return (
        <>
            {activeSessions.length > 0 && (
                <div className="mb-5 rounded-xl border bg-primary/5 p-4">
                    <h3 className="font-semibold">{t("active-sessions")}</h3>
                    <div className="mt-3 flex flex-wrap gap-2">
                        {activeSessions.map((session) => (
                            <Button
                                key={session.id}
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={() => onOpenSession(session)}
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
                <LoadingState />
            ) : (
                <div className="grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
                    <QuizFilters
                        gradeLevels={gradeLevels}
                        quizFilter={quizFilter}
                        gradeLevelFilter={gradeLevelFilter}
                        onQuizFilterChange={onQuizFilterChange}
                        onGradeLevelFilterChange={onGradeLevelFilterChange}
                        onDeleteGradeLevel={onDeleteGradeLevel}
                    />
                    <div className="min-w-0">
                        <h3 className="mb-4 font-semibold">
                            {t("exam-quizzes")}
                        </h3>
                        {loadError ? (
                            <p
                                role="alert"
                                className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
                            >
                                {loadError}
                            </p>
                        ) : quizzes.length === 0 &&
                          (quizFilter || gradeLevelFilter) ? (
                            <p className="rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                                {t("no-quiz-filtered")}
                            </p>
                        ) : quizzes.length === 0 ? (
                            <div className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                                <BookOpenText className="mb-2 size-8" />
                                <p className="font-medium">{t("no-quiz")}</p>
                                <p className="mt-1 text-sm">
                                    {t("no-quiz-help")}
                                </p>
                            </div>
                        ) : (
                            <>
                                <AnimatedGrid
                                    as="ul"
                                    ids={quizzes.map((quiz) => quiz.id)}
                                    className="gap-4 lg:grid-cols-2"
                                >
                                    {quizzes.map((quiz) => (
                                        <QuizCard
                                            key={quiz.id}
                                            quiz={quiz}
                                            onEdit={() => onEdit(quiz)}
                                            onPreview={() => onPreview(quiz)}
                                            onLaunch={() => onLaunch(quiz)}
                                            onDelete={() => onDelete(quiz)}
                                            onPrint={() => onPrint(quiz)}
                                        />
                                    ))}
                                </AnimatedGrid>
                                <Pagination
                                    currentPage={page}
                                    totalPages={totalPages}
                                    onPageChange={onPageChange}
                                />
                            </>
                        )}
                    </div>
                </div>
            )}
        </>
    )
}

function QuizFilters({
    gradeLevels,
    quizFilter,
    gradeLevelFilter,
    onQuizFilterChange,
    onGradeLevelFilterChange,
    onDeleteGradeLevel,
}: {
    gradeLevels: GradeLevel[]
    quizFilter: string
    gradeLevelFilter: string
    onQuizFilterChange: (value: string) => void
    onGradeLevelFilterChange: (value: string) => void
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
}) {
    const { t } = useTranslation()
    return (
        <FilterSidebar
            hasFilters={Boolean(quizFilter || gradeLevelFilter)}
            onClear={() => {
                onQuizFilterChange("")
                onGradeLevelFilterChange("")
            }}
        >
            <Field>
                <FieldLabel htmlFor="quiz-filter">{t("search")}</FieldLabel>
                <Input
                    id="quiz-filter"
                    value={quizFilter}
                    onChange={(event) => onQuizFilterChange(event.target.value)}
                    placeholder={t("search-quiz")}
                />
            </Field>
            <Field>
                <FieldLabel htmlFor="quiz-grade-filter">
                    {t("grade-level")}
                </FieldLabel>
                <GradeLevelSelect
                    id="quiz-grade-filter"
                    value={gradeLevelFilter}
                    levels={gradeLevels}
                    onChange={onGradeLevelFilterChange}
                    onDelete={onDeleteGradeLevel}
                    required={false}
                    placeholder={t("all-grade-levels")}
                />
            </Field>
        </FilterSidebar>
    )
}

function QuizCard({
    quiz,
    onEdit,
    onPreview,
    onLaunch,
    onDelete,
    onPrint,
}: {
    quiz: Quiz
    onEdit: () => void
    onPreview: () => void
    onLaunch: () => void
    onDelete: () => void
    onPrint: () => void
}) {
    const { t } = useTranslation()
    return (
        <li className="relative flex h-full flex-col rounded-xl border bg-background p-4">
            <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                className="absolute end-12 top-4 z-10"
                aria-label={t("edit-quiz-named", { title: quiz.title })}
                title={t("edit-quiz")}
                onClick={onEdit}
            >
                <Pencil />
            </Button>
            <Button
                type="button"
                size="icon-sm"
                variant="destructive"
                className="absolute end-4 top-4"
                aria-label={t("delete-quiz-named", { title: quiz.title })}
                title={t("delete-quiz")}
                onClick={onDelete}
            >
                <Trash2 />
            </Button>
            <div className="flex items-start gap-3 pe-20">
                <div className="min-w-0">
                    <h3 className="font-semibold break-words">{quiz.title}</h3>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t("quiz-summary", {
                            questions: quiz.question_count,
                            banks: quiz.question_banks.length,
                        })}
                    </p>
                </div>
            </div>
            <div className="mt-3 flex h-2 overflow-hidden rounded-full bg-muted">
                {difficultyKeys.map((difficulty) => (
                    <span
                        key={difficulty}
                        className={
                            difficulty === "easy"
                                ? "bg-emerald-500"
                                : difficulty === "medium"
                                  ? "bg-amber-500"
                                  : "bg-rose-500"
                        }
                        style={{
                            width: `${
                                (quiz[`${difficulty}_question_count`] /
                                    quiz.question_count) *
                                100
                            }%`,
                        }}
                    />
                ))}
            </div>
            <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                {difficultyKeys.map((difficulty) => (
                    <span key={difficulty}>
                        {t(`difficulty-${difficulty}`)}{" "}
                        {quiz[`${difficulty}_question_count`]}
                    </span>
                ))}
            </div>
            <p className="mt-3 text-xs text-muted-foreground">
                {quiz.question_banks
                    .map((bank) => `${bank.grade_level} — ${bank.chapter}`)
                    .join(" · ")}
            </p>
            <div className="mt-auto flex flex-wrap gap-2 pt-4">
                <Button type="button" size="sm" onClick={onLaunch}>
                    <Play />
                    {t("launch-quiz")}
                </Button>
                <div className="flex gap-2">
                    <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={onPreview}
                    >
                        <Eye />
                        {t("preview-quiz")}
                    </Button>
                    <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={onPrint}
                    >
                        <Printer />
                        {t("print-exams")}
                    </Button>
                </div>
            </div>
        </li>
    )
}

import type { Quiz, QuizSession } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { Pagination } from "@/components/ui/pagination"
import {
    BookOpenText,
    Eye,
    LoaderCircle,
    Pencil,
    Play,
    Trash2,
    UsersRound,
} from "lucide-react"
import { useTranslation } from "react-i18next"

const difficulties = ["easy", "medium", "hard"] as const
type QuizzesListProps = {
    quizzes: Quiz[]
    sessions: QuizSession[]
    gradeLevels: string[]
    isLoading: boolean
    loadError: string | null
    quizFilter: string
    gradeLevelFilter: string
    onQuizFilterChange: (value: string) => void
    onGradeLevelFilterChange: (value: string) => void
    onEdit: (quiz: Quiz) => void
    onPreview: (quiz: Quiz) => void
    onLaunch: (quiz: Quiz) => void
    onDelete: (quiz: Quiz) => void
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
    onEdit,
    onPreview,
    onLaunch,
    onDelete,
    onOpenSession,
    page,
    totalPages,
    onPageChange,
}: QuizzesListProps) {
    const { t } = useTranslation()

    return (
        <>
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
                <div className="flex min-h-40 items-center justify-center">
                    <LoaderCircle className="size-7 animate-spin text-primary" />
                </div>
            ) : loadError ? (
                <div className="grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
                    <QuizFilters
                        gradeLevels={gradeLevels}
                        quizFilter={quizFilter}
                        gradeLevelFilter={gradeLevelFilter}
                        onQuizFilterChange={onQuizFilterChange}
                        onGradeLevelFilterChange={onGradeLevelFilterChange}
                    />
                    <p
                        role="alert"
                        className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
                    >
                        {loadError}
                    </p>
                </div>
            ) : (
                <div className="grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
                    <QuizFilters
                        gradeLevels={gradeLevels}
                        quizFilter={quizFilter}
                        gradeLevelFilter={gradeLevelFilter}
                        onQuizFilterChange={onQuizFilterChange}
                        onGradeLevelFilterChange={onGradeLevelFilterChange}
                    />
                    {quizzes.length === 0 &&
                    (quizFilter || gradeLevelFilter) ? (
                        <p className="rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                            {t("no-quiz-filtered")}
                        </p>
                    ) : quizzes.length === 0 ? (
                        <div className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                            <BookOpenText className="mb-2 size-8" />
                            <p className="font-medium">{t("no-quiz")}</p>
                            <p className="mt-1 text-sm">{t("no-quiz-help")}</p>
                        </div>
                    ) : (
                        <div>
                            <ul
                                key={quizzes.map((quiz) => quiz.id).join(",")}
                                className="grid animate-in gap-4 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none lg:grid-cols-2"
                            >
                                {quizzes.map((quiz) => (
                                    <QuizCard
                                        key={quiz.id}
                                        quiz={quiz}
                                        onEdit={() => onEdit(quiz)}
                                        onPreview={() => onPreview(quiz)}
                                        onLaunch={() => onLaunch(quiz)}
                                        onDelete={() => onDelete(quiz)}
                                    />
                                ))}
                            </ul>
                            <Pagination
                                currentPage={page}
                                totalPages={totalPages}
                                onPageChange={onPageChange}
                            />
                        </div>
                    )}
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
}: {
    gradeLevels: string[]
    quizFilter: string
    gradeLevelFilter: string
    onQuizFilterChange: (value: string) => void
    onGradeLevelFilterChange: (value: string) => void
}) {
    const { t } = useTranslation()
    return (
        <aside className="h-fit rounded-xl border bg-background p-4">
            <h3 className="font-semibold">{t("filters")}</h3>
            <FieldGroup className="mt-4 gap-4">
                <Field>
                    <FieldLabel htmlFor="quiz-filter">{t("search")}</FieldLabel>
                    <Input
                        id="quiz-filter"
                        value={quizFilter}
                        onChange={(event) =>
                            onQuizFilterChange(event.target.value)
                        }
                        placeholder={t("search-quiz")}
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="quiz-grade-filter">
                        {t("grade-level")}
                    </FieldLabel>
                    <select
                        id="quiz-grade-filter"
                        className={NATIVE_SELECT_CLASS_NAME}
                        value={gradeLevelFilter}
                        onChange={(event) =>
                            onGradeLevelFilterChange(event.target.value)
                        }
                    >
                        <option value="">{t("all-grade-levels")}</option>
                        {gradeLevels.map((level) => (
                            <option key={level} value={level}>
                                {level}
                            </option>
                        ))}
                    </select>
                </Field>
                {(quizFilter || gradeLevelFilter) && (
                    <Button
                        type="button"
                        variant="outline"
                        onClick={() => {
                            onQuizFilterChange("")
                            onGradeLevelFilterChange("")
                        }}
                    >
                        {t("clear-filters")}
                    </Button>
                )}
            </FieldGroup>
        </aside>
    )
}

function QuizCard({
    quiz,
    onEdit,
    onPreview,
    onLaunch,
    onDelete,
}: {
    quiz: Quiz
    onEdit: () => void
    onPreview: () => void
    onLaunch: () => void
    onDelete: () => void
}) {
    const { t } = useTranslation()
    return (
        <li className="relative flex h-full flex-col rounded-xl border bg-background p-4">
            <Button
                type="button"
                size="icon-sm"
                variant="destructive"
                className="absolute top-4 right-4"
                aria-label={t("delete-quiz")}
                title={t("delete-quiz")}
                onClick={onDelete}
            >
                <Trash2 />
            </Button>
            <div className="flex items-start gap-3 pr-10">
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
                {difficulties.map((difficulty) => (
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
                {difficulties.map((difficulty) => (
                    <span key={difficulty}>
                        {t(`difficulty-${difficulty}`)}{" "}
                        {quiz[`${difficulty}_question_count`]}
                    </span>
                ))}
                <span className="font-semibold text-foreground">
                    {t("quiz-total-points", {
                        count:
                            quiz.easy_points +
                            quiz.medium_points +
                            quiz.hard_points,
                    })}
                </span>
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
                <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={onEdit}
                >
                    <Pencil />
                    {t("edit-quiz")}
                </Button>
                <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={onPreview}
                >
                    <Eye />
                    {t("preview-quiz")}
                </Button>
            </div>
        </li>
    )
}

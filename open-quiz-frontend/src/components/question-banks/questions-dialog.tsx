import {
    ANSWER_MODES,
    QUESTION_DIFFICULTIES,
    type AnswerMode,
    type Question,
} from "@/api/types"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import {
    ImageIcon,
    LoaderCircle,
    Pencil,
    Plus,
    Settings2,
    Trash2,
} from "lucide-react"
import { useMemo, useState } from "react"
import { useTranslation } from "react-i18next"
import { ChoiceImage } from "./choice-image"
import { CodeBlock } from "./code-block"
import { CODE_LANGUAGES } from "./code-languages"
import { QuestionImage } from "./question-image"

type QuestionsManagerProps = {
    questions: Question[]
    isLoading: boolean
    error: string | null
    onAdd: () => void
    onEdit: (question: Question) => void
    onDelete: (question: Question) => void
}

export function QuestionsManager({
    questions,
    isLoading,
    error,
    onAdd,
    onEdit,
    onDelete,
}: QuestionsManagerProps) {
    const { t } = useTranslation()
    const [sort, setSort] = useState("default")
    const [minimumPoints, setMinimumPoints] = useState("")
    const [maximumPoints, setMaximumPoints] = useState("")
    const [minimumDifficulty, setMinimumDifficulty] = useState("")
    const [maximumDifficulty, setMaximumDifficulty] = useState("")
    const [answerModes, setAnswerModes] = useState<AnswerMode[]>([])
    const visibleQuestions = useMemo(() => {
        const difficultyRank = new Map(
            QUESTION_DIFFICULTIES.map((difficulty, index) => [
                difficulty,
                index,
            ])
        )
        const minPoints = minimumPoints === "" ? null : Number(minimumPoints)
        const maxPoints = maximumPoints === "" ? null : Number(maximumPoints)
        const minDifficulty = minimumDifficulty
            ? (difficultyRank.get(
                  minimumDifficulty as (typeof QUESTION_DIFFICULTIES)[number]
              ) ?? null)
            : null
        const maxDifficulty = maximumDifficulty
            ? (difficultyRank.get(
                  maximumDifficulty as (typeof QUESTION_DIFFICULTIES)[number]
              ) ?? null)
            : null
        const pointsFor = (question: Question) =>
            question.choices.reduce(
                (total, choice) => total + Math.max(0, choice.points),
                0
            )
        const filtered = questions.filter((question) => {
            const points = pointsFor(question)
            const difficulty = difficultyRank.get(question.difficulty) ?? 0
            return (
                (minPoints === null || points >= minPoints) &&
                (maxPoints === null || points <= maxPoints) &&
                (minDifficulty === null || difficulty >= minDifficulty) &&
                (maxDifficulty === null || difficulty <= maxDifficulty) &&
                (answerModes.length === 0 ||
                    answerModes.includes(question.answer_mode))
            )
        })
        if (sort === "default") return filtered
        return [...filtered].sort((first, second) => {
            if (sort === "difficulty-asc" || sort === "difficulty-desc") {
                const difference =
                    (difficultyRank.get(first.difficulty) ?? 0) -
                    (difficultyRank.get(second.difficulty) ?? 0)
                return sort === "difficulty-asc" ? difference : -difference
            }
            const difference = pointsFor(first) - pointsFor(second)
            return sort === "points-asc" ? difference : -difference
        })
    }, [
        answerModes,
        maximumDifficulty,
        maximumPoints,
        minimumDifficulty,
        minimumPoints,
        questions,
        sort,
    ])
    const hasFilters = Boolean(
        minimumPoints ||
        maximumPoints ||
        minimumDifficulty ||
        maximumDifficulty ||
        answerModes.length
    )

    function toggleAnswerMode(mode: AnswerMode) {
        setAnswerModes((current) =>
            current.includes(mode)
                ? current.filter((item) => item !== mode)
                : [...current, mode]
        )
    }
    return (
        <section className="border-t pt-5">
            <div className="flex flex-wrap items-center justify-between gap-2">
                <div>
                    <h3 className="font-semibold">{t("bank-questions")}</h3>
                    <p className="text-xs text-muted-foreground">
                        {t("add-edit-questions")}
                    </p>
                </div>
                <Button type="button" onClick={onAdd}>
                    <Plus />
                    {t("add-question")}
                </Button>
            </div>
            <div className="mt-5 rounded-xl border bg-muted/20 p-4">
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                    <label className="grid gap-1 text-sm font-medium">
                        {t("question-sort")}
                        <select
                            className={NATIVE_SELECT_CLASS_NAME}
                            value={sort}
                            onChange={(event) => setSort(event.target.value)}
                        >
                            <option value="default">{t("sort-default")}</option>
                            <option value="difficulty-asc">
                                {t("sort-difficulty-asc")}
                            </option>
                            <option value="difficulty-desc">
                                {t("sort-difficulty-desc")}
                            </option>
                            <option value="points-asc">
                                {t("sort-points-asc")}
                            </option>
                            <option value="points-desc">
                                {t("sort-points-desc")}
                            </option>
                        </select>
                    </label>
                    <fieldset>
                        <legend className="text-sm font-medium">
                            {t("points-range")}
                        </legend>
                        <div className="mt-1 grid grid-cols-2 gap-2">
                            <Input
                                type="number"
                                min={0}
                                step="0.25"
                                value={minimumPoints}
                                placeholder={t("minimum")}
                                aria-label={t("minimum-points")}
                                onChange={(event) =>
                                    setMinimumPoints(event.target.value)
                                }
                            />
                            <Input
                                type="number"
                                min={0}
                                step="0.25"
                                value={maximumPoints}
                                placeholder={t("maximum")}
                                aria-label={t("maximum-points")}
                                onChange={(event) =>
                                    setMaximumPoints(event.target.value)
                                }
                            />
                        </div>
                    </fieldset>
                    <fieldset>
                        <legend className="text-sm font-medium">
                            {t("difficulty-range")}
                        </legend>
                        <div className="mt-1 grid grid-cols-2 gap-2">
                            <select
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={minimumDifficulty}
                                aria-label={t("minimum-difficulty")}
                                onChange={(event) =>
                                    setMinimumDifficulty(event.target.value)
                                }
                            >
                                <option value="">{t("minimum")}</option>
                                {QUESTION_DIFFICULTIES.map((difficulty) => (
                                    <option key={difficulty} value={difficulty}>
                                        {t(`difficulty-${difficulty}`)}
                                    </option>
                                ))}
                            </select>
                            <select
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={maximumDifficulty}
                                aria-label={t("maximum-difficulty")}
                                onChange={(event) =>
                                    setMaximumDifficulty(event.target.value)
                                }
                            >
                                <option value="">{t("maximum")}</option>
                                {QUESTION_DIFFICULTIES.map((difficulty) => (
                                    <option key={difficulty} value={difficulty}>
                                        {t(`difficulty-${difficulty}`)}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </fieldset>
                </div>
                <fieldset className="mt-4">
                    <legend className="text-sm font-medium">
                        {t("question-types")}
                    </legend>
                    <div className="mt-2 flex flex-wrap gap-2">
                        {ANSWER_MODES.map((mode) => (
                            <label
                                key={mode}
                                className="flex cursor-pointer items-center gap-2 rounded-lg border bg-background px-3 py-2 text-sm"
                            >
                                <input
                                    type="checkbox"
                                    checked={answerModes.includes(mode)}
                                    onChange={() => toggleAnswerMode(mode)}
                                />
                                {t(
                                    mode === "single"
                                        ? "single-choice"
                                        : mode === "multiple"
                                          ? "multiple-choice"
                                          : "written-answer"
                                )}
                            </label>
                        ))}
                        {hasFilters && (
                            <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={() => {
                                    setMinimumPoints("")
                                    setMaximumPoints("")
                                    setMinimumDifficulty("")
                                    setMaximumDifficulty("")
                                    setAnswerModes([])
                                }}
                            >
                                {t("clear-filters")}
                            </Button>
                        )}
                    </div>
                </fieldset>
            </div>
            <div className="mt-5">
                {isLoading ? (
                    <div
                        className="flex min-h-24 items-center justify-center"
                        role="status"
                        aria-label={t("page-loading")}
                    >
                        <LoaderCircle className="size-6 animate-spin text-primary motion-reduce:animate-none" />
                    </div>
                ) : error ? (
                    <p role="alert" className="mt-3 text-sm text-destructive">
                        {error}
                    </p>
                ) : questions.length === 0 ? (
                    <p className="mt-3 rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
                        {t("no-question")}
                    </p>
                ) : (
                    <ol className="max-h-[32rem] space-y-3 overflow-y-auto pr-1">
                        {visibleQuestions.map((question, index) => (
                            <QuestionCard
                                key={question.id}
                                question={question}
                                index={index}
                                onEdit={() => onEdit(question)}
                                onDelete={() => onDelete(question)}
                            />
                        ))}
                        {visibleQuestions.length === 0 && (
                            <li className="rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
                                {t("no-question-matches-filters")}
                            </li>
                        )}
                    </ol>
                )}
            </div>
        </section>
    )
}

function QuestionCard({
    question,
    index,
    onEdit,
    onDelete,
}: {
    question: Question
    index: number
    onEdit: () => void
    onDelete: () => void
}) {
    const { t } = useTranslation()
    return (
        <li className="rounded-xl border bg-background p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <p className="min-w-0 font-semibold break-words">
                    {index + 1}. {question.prompt}
                </p>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <span className="rounded-full bg-muted px-2 py-1 text-xs whitespace-nowrap">
                        {t(`difficulty-${question.difficulty}`)}
                    </span>
                    <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-semibold whitespace-nowrap text-primary">
                        {t("points-count", {
                            count: question.choices.reduce(
                                (total, choice) =>
                                    total + Math.max(0, choice.points),
                                0
                            ),
                        })}
                    </span>
                    <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={onEdit}
                    >
                        <Pencil />
                        {t("edit")}
                    </Button>
                    <Button
                        type="button"
                        size="icon"
                        variant="destructive"
                        aria-label={t("delete-question")}
                        title={t("delete-question")}
                        onClick={onDelete}
                    >
                        <Trash2 />
                    </Button>
                </div>
            </div>
            {question.has_image && (
                <>
                    <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                        <ImageIcon className="size-3.5" />
                        {t("image-attached")}
                    </div>
                    <QuestionImage
                        questionId={question.id}
                        alt={question.prompt}
                    />
                </>
            )}
            {question.code_content && question.code_language && (
                <div className="mt-3">
                    <CodeBlock
                        code={question.code_content}
                        language={question.code_language}
                    />
                </div>
            )}
            <ul
                className={`mt-3 grid gap-2 ${
                    question.answer_mode === "written" ? "" : "sm:grid-cols-2"
                }`}
            >
                {question.choices.map((choice) => (
                    <li
                        key={choice.id}
                        className="rounded-lg bg-muted/60 px-3 py-2 text-sm"
                    >
                        <div className="flex items-center gap-2">
                            {question.answer_mode !== "written" && (
                                <span
                                    className={
                                        choice.is_correct
                                            ? "text-primary"
                                            : "text-muted-foreground"
                                    }
                                >
                                    {choice.is_correct ? "✓" : "○"}
                                </span>
                            )}
                            <span className="min-w-0 flex-1 whitespace-pre-wrap">
                                {question.answer_mode === "written" && (
                                    <span className="mb-1 block text-xs font-semibold text-muted-foreground">
                                        {t("expected-written-answer")}
                                    </span>
                                )}
                                {choice.label}
                            </span>
                            <span className="font-semibold">
                                {t("points-count", { count: choice.points })}
                            </span>
                        </div>
                        {choice.has_image && (
                            <ChoiceImage
                                choiceId={choice.id}
                                alt={choice.label}
                            />
                        )}
                        {choice.code_content && choice.code_language && (
                            <div className="mt-2">
                                <CodeBlock
                                    code={choice.code_content}
                                    language={choice.code_language}
                                />
                            </div>
                        )}
                    </li>
                ))}
            </ul>
            <QuestionMetadata question={question} />
        </li>
    )
}

function QuestionMetadata({ question }: { question: Question }) {
    const { t } = useTranslation()
    const answerModeKey =
        question.answer_mode === "single"
            ? "single-choice"
            : question.answer_mode === "multiple"
              ? "multiple-choice"
              : "written-answer"
    const responseLanguage = question.response_language
        ? (CODE_LANGUAGES.find(
              (language) => language.value === question.response_language
          )?.label ?? question.response_language)
        : t("plain-text")

    return (
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
                <Settings2 className="size-3.5" />
                {t(answerModeKey)}
            </span>
            {question.answer_mode === "written" && (
                <>
                    <span>•</span>
                    <span>{responseLanguage}</span>
                </>
            )}
            {!question.answer_mode_disclosed && (
                <>
                    <span>•</span>
                    <span>{t("answer-mode-not-disclosed")}</span>
                </>
            )}
        </div>
    )
}

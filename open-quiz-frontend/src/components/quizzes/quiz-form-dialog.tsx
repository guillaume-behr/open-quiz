import type { GradeLevel, QuestionBank, Quiz } from "@/api/types"
import { GradeLevelSelect } from "@/components/grade-level-select"
import { DialogFormActions } from "@/components/forms/dialog-form-actions"
import { CollapsibleFilters } from "@/components/ui/collapsible-filters"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Pagination } from "@/components/ui/pagination"
import { Switch } from "@/components/ui/switch"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"

const difficultyKeys = ["easy", "medium", "hard"] as const
type Difficulty = (typeof difficultyKeys)[number]
type DifficultyValues = Record<Difficulty, number>
const BANK_PAGE_SIZE = 6

type QuizFormDialogProps = {
    open: boolean
    editingQuiz: Quiz | null
    banks: QuestionBank[]
    gradeLevels: GradeLevel[]
    quizGradeLevel: string
    title: string
    durationMinutes: number
    selectedBankIds: number[]
    allowPreviousQuestions: boolean
    allowNegativePoints: boolean
    sameQuestionsForAll: boolean
    difficultyCounts: DifficultyValues
    availableByDifficulty: DifficultyValues
    isBusy: boolean
    error: string | null
    onTitleChange: (value: string) => void
    onDurationChange: (value: number) => void
    onQuizGradeLevelChange: (value: string) => void
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    onSelectedBankIdsChange: (ids: number[]) => void
    onAllowPreviousQuestionsChange: (value: boolean) => void
    onAllowNegativePointsChange: (value: boolean) => void
    onSameQuestionsForAllChange: (value: boolean) => void
    onDifficultyCountsChange: (values: DifficultyValues) => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function QuizFormDialog({
    open,
    editingQuiz,
    banks,
    gradeLevels,
    quizGradeLevel,
    title,
    durationMinutes,
    selectedBankIds,
    allowPreviousQuestions,
    allowNegativePoints,
    sameQuestionsForAll,
    difficultyCounts,
    availableByDifficulty,
    isBusy,
    error,
    onTitleChange,
    onDurationChange,
    onQuizGradeLevelChange,
    onDeleteGradeLevel,
    onSelectedBankIdsChange,
    onAllowPreviousQuestionsChange,
    onAllowNegativePointsChange,
    onSameQuestionsForAllChange,
    onDifficultyCountsChange,
    onClose,
    onSubmit,
}: QuizFormDialogProps) {
    const { t } = useTranslation()
    const questionCount = Object.values(difficultyCounts).reduce(
        (total, count) => total + count,
        0
    )

    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen && !isBusy) onClose()
            }}
            title={t(editingQuiz ? "edit-exam-quiz" : "create-exam-quiz")}
            description={t("create-exam-quiz-help")}
            size="xl"
        >
            <form onSubmit={onSubmit}>
                <FieldGroup className="gap-5">
                    <div className="grid gap-4 md:grid-cols-2">
                        <Field>
                            <FieldLabel htmlFor="quiz-title">
                                {t("quiz-title")}
                            </FieldLabel>
                            <Input
                                id="quiz-title"
                                value={title}
                                onChange={(event) =>
                                    onTitleChange(event.target.value)
                                }
                                maxLength={160}
                                required
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="quiz-grade-level">
                                {t("grade-level")}
                            </FieldLabel>
                            <GradeLevelSelect
                                id="quiz-grade-level"
                                value={quizGradeLevel}
                                levels={gradeLevels}
                                onChange={onQuizGradeLevelChange}
                                onDelete={onDeleteGradeLevel}
                                disabled={isBusy}
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
                                    onDurationChange(
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
                    </div>
                    {quizGradeLevel && (
                        <QuestionBankPicker
                            banks={banks}
                            gradeLevel={quizGradeLevel}
                            selectedIds={selectedBankIds}
                            onSelectedIdsChange={onSelectedBankIdsChange}
                        />
                    )}
                    <section className="space-y-3 rounded-xl border bg-muted/20 p-4">
                        <div>
                            <h2 className="font-semibold">
                                {t("quiz-options")}
                            </h2>
                            <p className="text-xs text-muted-foreground">
                                {t("quiz-options-help")}
                            </p>
                        </div>
                        <div className="grid gap-3 md:grid-cols-2">
                            <label className="flex cursor-pointer items-center justify-between gap-4 rounded-lg border bg-background p-4">
                                <span>
                                    <span className="block font-medium">
                                        {t("allow-previous-questions")}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                        {t("allow-previous-questions-help")}
                                    </span>
                                </span>
                                <Switch
                                    checked={allowPreviousQuestions}
                                    onCheckedChange={
                                        onAllowPreviousQuestionsChange
                                    }
                                    aria-label={t("allow-previous-questions")}
                                />
                            </label>
                            <label className="flex cursor-pointer items-center justify-between gap-4 rounded-lg border bg-background p-4">
                                <span>
                                    <span className="block font-medium">
                                        {t("same-questions-for-all")}
                                    </span>
                                    <span className="text-xs text-muted-foreground">
                                        {t("same-questions-for-all-help")}
                                    </span>
                                </span>
                                <Switch
                                    checked={sameQuestionsForAll}
                                    onCheckedChange={
                                        onSameQuestionsForAllChange
                                    }
                                    aria-label={t("same-questions-for-all")}
                                />
                            </label>
                            <label className="flex cursor-pointer items-center justify-between gap-4 rounded-lg border bg-background p-4">
                                <span className="font-medium">
                                    {t("allow-negative-points")}
                                </span>
                                <Switch
                                    checked={allowNegativePoints}
                                    onCheckedChange={
                                        onAllowNegativePointsChange
                                    }
                                    aria-label={t("allow-negative-points")}
                                />
                            </label>
                        </div>
                    </section>
                    <DifficultyQuestionCounts
                        counts={difficultyCounts}
                        available={availableByDifficulty}
                        hasSelectedBanks={selectedBankIds.length > 0}
                        onChange={onDifficultyCountsChange}
                    />
                    {error && <FieldError>{error}</FieldError>}
                    <DialogFormActions
                        isBusy={isBusy}
                        isEditing={Boolean(editingQuiz)}
                        submitLabel={t(
                            editingQuiz ? "save-quiz" : "create-quiz"
                        )}
                        submitDisabled={
                            !quizGradeLevel ||
                            selectedBankIds.length === 0 ||
                            questionCount === 0
                        }
                        onClose={onClose}
                    />
                </FieldGroup>
            </form>
        </Dialog>
    )
}

function QuestionBankPicker({
    banks,
    gradeLevel,
    selectedIds,
    onSelectedIdsChange,
}: {
    banks: QuestionBank[]
    gradeLevel: string
    selectedIds: number[]
    onSelectedIdsChange: (ids: number[]) => void
}) {
    const { t } = useTranslation()
    const [search, setSearch] = useState("")
    const [page, setPage] = useState(1)

    const trimmedSearch = search.trim().toLowerCase()
    const filtered = banks.filter(
        (bank) =>
            bank.grade_level === gradeLevel &&
            (trimmedSearch === "" ||
                bank.chapter.toLowerCase().includes(trimmedSearch))
    )
    const totalPages = Math.max(1, Math.ceil(filtered.length / BANK_PAGE_SIZE))
    const safePage = Math.min(page, totalPages)
    const visible = filtered.slice(
        (safePage - 1) * BANK_PAGE_SIZE,
        safePage * BANK_PAGE_SIZE
    )

    function toggle(bankId: number) {
        onSelectedIdsChange(
            selectedIds.includes(bankId)
                ? selectedIds.filter((id) => id !== bankId)
                : [...selectedIds, bankId]
        )
    }

    return (
        <Field>
            <FieldLabel htmlFor="quiz-bank-search">
                {t("quiz-question-banks")}
            </FieldLabel>
            <CollapsibleFilters activeCount={Number(Boolean(trimmedSearch))}>
                <Input
                    id="quiz-bank-search"
                    className="max-w-md"
                    value={search}
                    placeholder={t("search-question-bank")}
                    aria-label={t("search-question-bank")}
                    onChange={(event) => {
                        setSearch(event.target.value)
                        setPage(1)
                    }}
                />
            </CollapsibleFilters>
            {filtered.length === 0 ? (
                <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                    {t("quiz-needs-question-bank")}
                </p>
            ) : (
                <>
                    <div className="mt-2 grid gap-2 sm:grid-cols-2">
                        {visible.map((bank) => {
                            const selected = selectedIds.includes(bank.id)
                            return (
                                <label
                                    key={bank.id}
                                    className={`flex cursor-pointer gap-3 rounded-lg border p-3 transition-colors focus-within:border-primary focus-within:ring-3 focus-within:ring-primary/20 ${
                                        selected
                                            ? "border-primary bg-primary/5"
                                            : ""
                                    }`}
                                >
                                    <input
                                        type="checkbox"
                                        className="mt-1 accent-primary"
                                        checked={selected}
                                        onChange={() => toggle(bank.id)}
                                    />
                                    <span className="min-w-0">
                                        <span className="block font-medium">
                                            {bank.chapter}
                                        </span>
                                        <span className="text-xs text-muted-foreground">
                                            {t("question-count", {
                                                count: bank.question_count,
                                            })}
                                        </span>
                                    </span>
                                </label>
                            )
                        })}
                    </div>
                    <Pagination
                        currentPage={safePage}
                        totalPages={totalPages}
                        onPageChange={setPage}
                    />
                </>
            )}
        </Field>
    )
}

function DifficultyQuestionCounts({
    counts,
    available,
    hasSelectedBanks,
    onChange,
}: {
    counts: DifficultyValues
    available: DifficultyValues
    hasSelectedBanks: boolean
    onChange: (values: DifficultyValues) => void
}) {
    const { t } = useTranslation()
    const total = counts.easy + counts.medium + counts.hard
    const maximumFor = (difficulty: Difficulty) =>
        Math.min(available[difficulty], 200 - total + counts[difficulty])

    return (
        <Field>
            <FieldLabel>{t("quiz-difficulty-counts")}</FieldLabel>
            <p className="text-xs text-muted-foreground">
                {t("quiz-difficulty-count-help")}
            </p>
            <div className="mt-2 grid gap-3 sm:grid-cols-3">
                {difficultyKeys.map((difficulty) => (
                    <div key={difficulty}>
                        <FieldLabel htmlFor={`quiz-${difficulty}`}>
                            {t(`difficulty-${difficulty}`)}
                        </FieldLabel>
                        <Input
                            id={`quiz-${difficulty}`}
                            type="number"
                            min={0}
                            max={maximumFor(difficulty)}
                            value={counts[difficulty]}
                            disabled={!hasSelectedBanks}
                            onChange={(event) =>
                                onChange({
                                    ...counts,
                                    [difficulty]: Math.min(
                                        maximumFor(difficulty),
                                        Math.max(0, Number(event.target.value))
                                    ),
                                })
                            }
                            required
                        />
                        <p className="mt-1 text-xs text-muted-foreground">
                            {t("difficulty-available", {
                                count: available[difficulty],
                            })}
                        </p>
                    </div>
                ))}
            </div>
            <p className="mt-3 text-sm font-semibold text-primary">
                {t("quiz-total-questions", { count: total })}
            </p>
            {hasSelectedBanks && total === 0 && (
                <FieldError>{t("quiz-needs-question")}</FieldError>
            )}
        </Field>
    )
}

import type { QuestionBank, Quiz } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { LoaderCircle, Pencil, Plus } from "lucide-react"
import type { FormEvent } from "react"
import { useTranslation } from "react-i18next"

const difficultyKeys = ["easy", "medium", "hard"] as const
type Difficulty = (typeof difficultyKeys)[number]
type DifficultyValues = Record<Difficulty, number>

type QuizFormDialogProps = {
    mode: "exam"
    open: boolean
    editingQuiz: Quiz | null
    banks: QuestionBank[]
    title: string
    durationMinutes: number
    selectedBankIds: number[]
    allowPreviousQuestions: boolean
    sameQuestionsForAll: boolean
    difficultyCounts: DifficultyValues
    difficultyPoints: DifficultyValues
    availableByDifficulty: DifficultyValues
    isBusy: boolean
    error: string | null
    onTitleChange: (value: string) => void
    onDurationChange: (value: number) => void
    onSelectedBankIdsChange: (ids: number[]) => void
    onAllowPreviousQuestionsChange: (value: boolean) => void
    onSameQuestionsForAllChange: (value: boolean) => void
    onDifficultyCountsChange: (values: DifficultyValues) => void
    onDifficultyPointsChange: (values: DifficultyValues) => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function QuizFormDialog({
    mode,
    open,
    editingQuiz,
    banks,
    title,
    durationMinutes,
    selectedBankIds,
    allowPreviousQuestions,
    sameQuestionsForAll,
    difficultyCounts,
    difficultyPoints,
    availableByDifficulty,
    isBusy,
    error,
    onTitleChange,
    onDurationChange,
    onSelectedBankIdsChange,
    onAllowPreviousQuestionsChange,
    onSameQuestionsForAllChange,
    onDifficultyCountsChange,
    onDifficultyPointsChange,
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
        >
            <form onSubmit={onSubmit}>
                <FieldGroup className="gap-5">
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
                    {mode === "exam" && (
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
                    )}
                    {mode === "exam" && (
                        <Field>
                            <label className="flex cursor-pointer items-center justify-between gap-4 rounded-lg border p-4">
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
                        </Field>
                    )}
                    <QuestionBankPicker
                        banks={banks}
                        selectedIds={selectedBankIds}
                        onSelectedIdsChange={onSelectedBankIdsChange}
                    />
                    {mode === "exam" && (
                        <Field>
                            <label className="flex cursor-pointer items-center justify-between gap-4 rounded-lg border p-4">
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
                        </Field>
                    )}
                    <DifficultyQuestionCounts
                        mode={mode}
                        counts={difficultyCounts}
                        points={difficultyPoints}
                        available={availableByDifficulty}
                        hasSelectedBanks={selectedBankIds.length > 0}
                        onChange={onDifficultyCountsChange}
                        onPointsChange={onDifficultyPointsChange}
                    />
                    {error && <FieldError>{error}</FieldError>}
                    <div className="flex justify-end gap-2 border-t pt-4">
                        <Button
                            type="button"
                            variant="outline"
                            disabled={isBusy}
                            onClick={onClose}
                        >
                            {t("cancel")}
                        </Button>
                        <Button
                            type="submit"
                            disabled={
                                isBusy ||
                                selectedBankIds.length === 0 ||
                                questionCount === 0
                            }
                        >
                            {isBusy ? (
                                <LoaderCircle className="animate-spin" />
                            ) : editingQuiz ? (
                                <Pencil />
                            ) : (
                                <Plus />
                            )}
                            {t(editingQuiz ? "save-quiz" : "create-quiz")}
                        </Button>
                    </div>
                </FieldGroup>
            </form>
        </Dialog>
    )
}

function QuestionBankPicker({
    banks,
    selectedIds,
    onSelectedIdsChange,
}: {
    banks: QuestionBank[]
    selectedIds: number[]
    onSelectedIdsChange: (ids: number[]) => void
}) {
    const { t } = useTranslation()
    return (
        <Field>
            <FieldLabel>{t("quiz-question-banks")}</FieldLabel>
            {banks.length === 0 ? (
                <p className="rounded-lg border border-dashed p-4 text-sm text-muted-foreground">
                    {t("quiz-needs-question-bank")}
                </p>
            ) : (
                <div className="grid gap-2 sm:grid-cols-2">
                    {banks.map((bank) => {
                        const selected = selectedIds.includes(bank.id)
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
                                        onSelectedIdsChange(
                                            selected
                                                ? selectedIds.filter(
                                                      (id) => id !== bank.id
                                                  )
                                                : [...selectedIds, bank.id]
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
    )
}

function DifficultyQuestionCounts({
    mode,
    counts,
    points,
    available,
    hasSelectedBanks,
    onChange,
    onPointsChange,
}: {
    mode: "exam" | "training"
    counts: DifficultyValues
    points: DifficultyValues
    available: DifficultyValues
    hasSelectedBanks: boolean
    onChange: (values: DifficultyValues) => void
    onPointsChange: (values: DifficultyValues) => void
}) {
    const { t } = useTranslation()
    const total = counts.easy + counts.medium + counts.hard
    const totalPoints = points.easy + points.medium + points.hard
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
                        {mode === "exam" && (
                            <div className="mt-3">
                                <FieldLabel
                                    htmlFor={`quiz-${difficulty}-points`}
                                >
                                    {t("quiz-difficulty-points", {
                                        difficulty: t(
                                            `difficulty-${difficulty}`
                                        ),
                                    })}
                                </FieldLabel>
                                <Input
                                    id={`quiz-${difficulty}-points`}
                                    type="number"
                                    min={0}
                                    max={10000}
                                    step="0.25"
                                    value={points[difficulty]}
                                    disabled={counts[difficulty] === 0}
                                    onChange={(event) =>
                                        onPointsChange({
                                            ...points,
                                            [difficulty]: Math.min(
                                                10000,
                                                Math.max(
                                                    0,
                                                    Number(event.target.value)
                                                )
                                            ),
                                        })
                                    }
                                    required
                                />
                                {counts[difficulty] > 0 && (
                                    <p className="mt-1 text-xs text-muted-foreground">
                                        {t("quiz-points-per-question", {
                                            count: Number(
                                                (
                                                    points[difficulty] /
                                                    counts[difficulty]
                                                ).toFixed(2)
                                            ),
                                        })}
                                    </p>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>
            <p className="mt-3 text-sm font-semibold text-primary">
                {t("quiz-total-questions", { count: total })}
                {mode === "exam" && (
                    <> · {t("quiz-total-points", { count: totalPoints })}</>
                )}
            </p>
            {hasSelectedBanks && total === 0 && (
                <FieldError>{t("quiz-needs-question")}</FieldError>
            )}
        </Field>
    )
}

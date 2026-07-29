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
    open: boolean
    editingQuiz: Quiz | null
    banks: QuestionBank[]
    title: string
    durationMinutes: number
    selectedBankIds: number[]
    allowPreviousQuestions: boolean
    questionCount: number
    percentages: DifficultyValues
    difficultyPreview: DifficultyValues
    availableByDifficulty: DifficultyValues
    previewQuestionTotal: number
    isBusy: boolean
    error: string | null
    onTitleChange: (value: string) => void
    onDurationChange: (value: number) => void
    onSelectedBankIdsChange: (ids: number[]) => void
    onAllowPreviousQuestionsChange: (value: boolean) => void
    onQuestionCountChange: (value: number) => void
    onPercentagesChange: (values: DifficultyValues) => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function QuizFormDialog({
    open,
    editingQuiz,
    banks,
    title,
    durationMinutes,
    selectedBankIds,
    allowPreviousQuestions,
    questionCount,
    percentages,
    difficultyPreview,
    availableByDifficulty,
    previewQuestionTotal,
    isBusy,
    error,
    onTitleChange,
    onDurationChange,
    onSelectedBankIdsChange,
    onAllowPreviousQuestionsChange,
    onQuestionCountChange,
    onPercentagesChange,
    onClose,
    onSubmit,
}: QuizFormDialogProps) {
    const { t } = useTranslation()
    const percentageTotal =
        percentages.easy + percentages.medium + percentages.hard

    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen && !isBusy) onClose()
            }}
            title={t(editingQuiz ? "edit-quiz" : "create-quiz")}
            description={t("create-quiz-help")}
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
                                        Math.max(1, Number(event.target.value))
                                    )
                                )
                            }
                            required
                        />
                        <p className="text-xs text-muted-foreground">
                            {t("quiz-duration-help")}
                        </p>
                    </Field>
                    <QuestionBankPicker
                        banks={banks}
                        selectedIds={selectedBankIds}
                        onSelectedIdsChange={onSelectedBankIdsChange}
                    />
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
                                onCheckedChange={onAllowPreviousQuestionsChange}
                                aria-label={t("allow-previous-questions")}
                            />
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
                                onQuestionCountChange(
                                    Math.max(1, Number(event.target.value))
                                )
                            }
                            required
                        />
                    </Field>
                    <DifficultyDistribution
                        percentages={percentages}
                        preview={difficultyPreview}
                        available={availableByDifficulty}
                        previewTotal={previewQuestionTotal}
                        questionCount={questionCount}
                        hasSelectedBanks={selectedBankIds.length > 0}
                        onChange={onPercentagesChange}
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
                                percentageTotal !== 100 ||
                                selectedBankIds.length === 0 ||
                                previewQuestionTotal < questionCount
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

function DifficultyDistribution({
    percentages,
    preview,
    available,
    previewTotal,
    questionCount,
    hasSelectedBanks,
    onChange,
}: {
    percentages: DifficultyValues
    preview: DifficultyValues
    available: DifficultyValues
    previewTotal: number
    questionCount: number
    hasSelectedBanks: boolean
    onChange: (values: DifficultyValues) => void
}) {
    const { t } = useTranslation()
    const total = percentages.easy + percentages.medium + percentages.hard

    return (
        <Field>
            <div className="flex items-center justify-between gap-3">
                <FieldLabel>{t("difficulty-distribution")}</FieldLabel>
                <span
                    className={`text-sm font-semibold ${
                        total === 100 ? "text-primary" : "text-destructive"
                    }`}
                >
                    {total} %
                </span>
            </div>
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
                            max={100}
                            value={percentages[difficulty]}
                            onChange={(event) =>
                                onChange({
                                    ...percentages,
                                    [difficulty]: Math.min(
                                        100,
                                        Math.max(0, Number(event.target.value))
                                    ),
                                })
                            }
                            required
                        />
                    </div>
                ))}
            </div>
            {total !== 100 && (
                <FieldError>{t("difficulty-total-error")}</FieldError>
            )}
            {hasSelectedBanks && total === 100 && (
                <div className="mt-4 rounded-lg border bg-muted/30 p-3">
                    <p className="text-sm font-medium">
                        {t("difficulty-preview")}
                    </p>
                    <div className="mt-2 grid grid-cols-3 gap-2">
                        {difficultyKeys.map((difficulty) => (
                            <div
                                key={difficulty}
                                className="rounded-md bg-background p-2 text-center"
                            >
                                <p className="text-lg font-bold text-primary">
                                    {preview[difficulty]}
                                </p>
                                <p className="text-xs text-muted-foreground">
                                    {t(`difficulty-${difficulty}`)} ·{" "}
                                    {t("difficulty-available", {
                                        count: available[difficulty],
                                    })}
                                </p>
                            </div>
                        ))}
                    </div>
                    {previewTotal < questionCount && (
                        <FieldError className="mt-2">
                            {t("quiz-insufficient-total-questions", {
                                available: previewTotal,
                                requested: questionCount,
                            })}
                        </FieldError>
                    )}
                </div>
            )}
        </Field>
    )
}

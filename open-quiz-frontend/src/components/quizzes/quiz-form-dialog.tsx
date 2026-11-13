import type { GradeLevel, QuestionBank } from "@/api/types"
import { GradeLevelSelect } from "@/components/grade-level-select"
import { DialogFormActions } from "@/components/forms/dialog-form-actions"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Switch } from "@/components/ui/switch"
import { type Dispatch, type FormEvent } from "react"
import { useTranslation } from "react-i18next"
import { DifficultyQuestionCounts } from "./difficulty-question-counts"
import { DurationInput } from "./duration-input"
import { QuestionBankPicker } from "./quiz-bank-picker"
import {
    availableQuestionCounts,
    type QuizFormAction,
    type QuizFormState,
} from "./quiz-form-state"

type QuizFormDialogProps = {
    open: boolean
    /** The quiz being created or edited, and how to change it. */
    form: QuizFormState
    dispatch: Dispatch<QuizFormAction>
    banks: QuestionBank[]
    gradeLevels: GradeLevel[]
    isBusy: boolean
    error: string | null
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

/** The yes/no options of a quiz, in the order the form shows them. */
const QUIZ_OPTIONS = [
    {
        field: "allowPreviousQuestions",
        label: "allow-previous-questions",
        help: "allow-previous-questions-help",
    },
    {
        field: "allowAnswerReview",
        label: "allow-answer-review",
        help: "allow-answer-review-help",
    },
    {
        field: "showProvisionalGrades",
        label: "show-provisional-grades",
        help: "show-provisional-grades-help",
    },
    {
        field: "sameQuestionsForAll",
        label: "same-questions-for-all",
        help: "same-questions-for-all-help",
    },
    {
        field: "allowNegativePoints",
        label: "allow-negative-points",
        help: null,
    },
] as const satisfies readonly {
    field: keyof QuizFormState
    label: string
    help: string | null
}[]

export function QuizFormDialog({
    open,
    form,
    dispatch,
    banks,
    gradeLevels,
    isBusy,
    error,
    onDeleteGradeLevel,
    onClose,
    onSubmit,
}: QuizFormDialogProps) {
    const {
        editingQuiz,
        gradeLevel: quizGradeLevel,
        selectedBankIds,
        difficultyCounts,
    } = form
    const { t } = useTranslation()
    const questionCount = Object.values(difficultyCounts).reduce(
        (total, count) => total + count,
        0
    )
    const availableByDifficulty = availableQuestionCounts(
        banks,
        selectedBankIds
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
                                value={form.title}
                                onChange={(event) =>
                                    dispatch({
                                        type: "set",
                                        field: "title",
                                        value: event.target.value,
                                    })
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
                                onChange={(gradeLevel) =>
                                    dispatch({
                                        type: "grade-level",
                                        gradeLevel,
                                    })
                                }
                                onDelete={onDeleteGradeLevel}
                                disabled={isBusy}
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="quiz-duration">
                                {t("quiz-duration")}
                            </FieldLabel>
                            <DurationInput
                                value={form.durationMinutes}
                                onChange={(value) =>
                                    dispatch({
                                        type: "set",
                                        field: "durationMinutes",
                                        value,
                                    })
                                }
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
                            onSelectedIdsChange={(ids) =>
                                dispatch({ type: "banks", ids, banks })
                            }
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
                            {QUIZ_OPTIONS.map(({ field, label, help }) => (
                                <label
                                    key={field}
                                    className="flex cursor-pointer items-center justify-between gap-4 rounded-lg border bg-background p-4"
                                >
                                    {help ? (
                                        <span>
                                            <span className="block font-medium">
                                                {t(label)}
                                            </span>
                                            <span className="text-xs text-muted-foreground">
                                                {t(help)}
                                            </span>
                                        </span>
                                    ) : (
                                        <span className="font-medium">
                                            {t(label)}
                                        </span>
                                    )}
                                    <Switch
                                        checked={form[field]}
                                        onCheckedChange={(value) =>
                                            dispatch({
                                                type: "set",
                                                field,
                                                value,
                                            })
                                        }
                                        aria-label={t(label)}
                                    />
                                </label>
                            ))}
                        </div>
                    </section>
                    <DifficultyQuestionCounts
                        counts={difficultyCounts}
                        available={availableByDifficulty}
                        hasSelectedBanks={selectedBankIds.length > 0}
                        onChange={(value) =>
                            dispatch({
                                type: "set",
                                field: "difficultyCounts",
                                value,
                            })
                        }
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

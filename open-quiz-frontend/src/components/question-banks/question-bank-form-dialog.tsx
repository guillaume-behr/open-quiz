import type { GradeLevel, QuestionBank } from "@/api/types"
import { DialogFormActions } from "@/components/forms/dialog-form-actions"
import { GradeLevelField } from "@/components/forms/grade-level-field"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import type { FormEvent, ReactNode } from "react"
import { useTranslation } from "react-i18next"

type QuestionBankFormDialogProps = {
    open: boolean
    editingBank: QuestionBank | null
    gradeLevels: GradeLevel[]
    gradeLevel: string
    title: string
    newGradeLevel: string
    isAddingGradeLevel: boolean
    isBusy: boolean
    error: string | null
    onGradeLevelChange: (value: string) => void
    onTitleChange: (value: string) => void
    onNewGradeLevelChange: (value: string) => void
    onAddingGradeLevelChange: (value: boolean) => void
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    onAddGradeLevel: () => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
    questionManagement?: ReactNode
}

export function QuestionBankFormDialog({
    open,
    editingBank,
    gradeLevels,
    gradeLevel,
    title,
    newGradeLevel,
    isAddingGradeLevel,
    isBusy,
    error,
    onGradeLevelChange,
    onTitleChange,
    onNewGradeLevelChange,
    onAddingGradeLevelChange,
    onDeleteGradeLevel,
    onAddGradeLevel,
    onClose,
    onSubmit,
    questionManagement,
}: QuestionBankFormDialogProps) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen && !isBusy) onClose()
            }}
            title={t(
                editingBank ? "edit-question-bank" : "create-question-bank"
            )}
            description={t("create-question-bank-help")}
            size={editingBank ? "xl" : "md"}
        >
            <form onSubmit={onSubmit}>
                <FieldGroup className="gap-4">
                    <div className="grid items-start gap-4 md:grid-cols-2">
                        <Field>
                            <FieldLabel htmlFor="question-bank-title">
                                {t("question-bank-title")}
                            </FieldLabel>
                            <Input
                                id="question-bank-title"
                                value={title}
                                onChange={(event) =>
                                    onTitleChange(event.target.value)
                                }
                                maxLength={160}
                                placeholder={t(
                                    "question-bank-title-placeholder"
                                )}
                                required
                            />
                        </Field>
                        <GradeLevelField
                            id="question-bank-grade-level"
                            value={gradeLevel}
                            levels={gradeLevels}
                            newValue={newGradeLevel}
                            isAdding={isAddingGradeLevel}
                            disabled={isBusy}
                            onChange={onGradeLevelChange}
                            onNewValueChange={onNewGradeLevelChange}
                            onAddingChange={onAddingGradeLevelChange}
                            onDelete={onDeleteGradeLevel}
                            onAdd={onAddGradeLevel}
                        />
                    </div>
                    {editingBank && questionManagement}
                    {error && <FieldError>{error}</FieldError>}
                    <DialogFormActions
                        isBusy={isBusy}
                        isEditing={Boolean(editingBank)}
                        submitLabel={t(
                            isBusy
                                ? editingBank
                                    ? "saving-question-bank"
                                    : "creating-question-bank"
                                : editingBank
                                  ? "save-question-bank"
                                  : "create-question-bank-action"
                        )}
                        onClose={onClose}
                    />
                </FieldGroup>
            </form>
        </Dialog>
    )
}

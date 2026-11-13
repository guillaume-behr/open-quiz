import type { GradeLevel, QuestionBank } from "@/api/types"
import { DialogFormActions } from "@/components/forms/dialog-form-actions"
import { GradeLevelField } from "@/components/grade-levels/grade-level-field"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { type FormEvent, type ReactNode, useState } from "react"
import { useTranslation } from "react-i18next"

type QuestionBankFormDialogProps = {
    open: boolean
    editingBank: QuestionBank | null
    gradeLevels: GradeLevel[]
    isBusy: boolean
    error: string | null
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    /** Creates a grade level; null when it failed (the error is shown). */
    onAddGradeLevel: (name: string) => Promise<GradeLevel | null>
    onClose: () => void
    onSubmit: (values: { grade_level: string; chapter: string }) => void
    questionManagement?: ReactNode
}

/**
 * Creates a question bank, or edits one with its questions. Mount it while
 * the bank is being created or edited, keyed by the bank, so each opening
 * starts from that bank; `open` only hides it while a question is edited.
 */
export function QuestionBankFormDialog({
    open,
    editingBank,
    gradeLevels,
    isBusy,
    error,
    onDeleteGradeLevel,
    onAddGradeLevel,
    onClose,
    onSubmit,
    questionManagement,
}: QuestionBankFormDialogProps) {
    const { t } = useTranslation()
    const [gradeLevel, setGradeLevel] = useState(editingBank?.grade_level ?? "")
    const [title, setTitle] = useState(editingBank?.chapter ?? "")
    const [newGradeLevel, setNewGradeLevel] = useState("")
    const [isAddingGradeLevel, setIsAddingGradeLevel] = useState(false)

    async function addGradeLevel() {
        const normalizedLevel = newGradeLevel.trim()
        if (!normalizedLevel) return
        const created = await onAddGradeLevel(normalizedLevel)
        if (!created) return
        setGradeLevel(created.name)
        setNewGradeLevel("")
        setIsAddingGradeLevel(false)
    }

    function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        onSubmit({ grade_level: gradeLevel.trim(), chapter: title.trim() })
    }

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
            <FieldGroup className="gap-4">
                <form id="question-bank-form" onSubmit={submit}>
                    <div className="grid items-start gap-4 md:grid-cols-2">
                        <Field>
                            <FieldLabel htmlFor="question-bank-title">
                                {t("question-bank-title")}
                            </FieldLabel>
                            <Input
                                id="question-bank-title"
                                value={title}
                                onChange={(event) =>
                                    setTitle(event.target.value)
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
                            onChange={setGradeLevel}
                            onNewValueChange={setNewGradeLevel}
                            onAddingChange={setIsAddingGradeLevel}
                            onDelete={onDeleteGradeLevel}
                            onAdd={() => void addGradeLevel()}
                        />
                    </div>
                </form>
                {/* Outside the form: Enter in these inputs must not save it. */}
                {editingBank && questionManagement}
                {error && <FieldError>{error}</FieldError>}
                <DialogFormActions
                    form="question-bank-form"
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
        </Dialog>
    )
}

import type { GradeLevel, StudentClass } from "@/api/types"
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
import { formatClassName } from "@/lib/utils"
import type { FormEvent } from "react"
import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"

type ClassFormDialogProps = {
    open: boolean
    editingClass: StudentClass | null
    classes: StudentClass[]
    gradeLevels: GradeLevel[]
    className: string
    gradeLevel: string
    newGradeLevel: string
    isAddingGradeLevel: boolean
    isBusy: boolean
    error: string | null
    onClassNameChange: (value: string) => void
    onGradeLevelChange: (value: string) => void
    onNewGradeLevelChange: (value: string) => void
    onAddingGradeLevelChange: (value: boolean) => void
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    onAddGradeLevel: () => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
    studentManagement?: ReactNode
}

export function ClassFormDialog({
    open,
    editingClass,
    classes,
    gradeLevels,
    className,
    gradeLevel,
    newGradeLevel,
    isAddingGradeLevel,
    isBusy,
    error,
    onClassNameChange,
    onGradeLevelChange,
    onNewGradeLevelChange,
    onAddingGradeLevelChange,
    onDeleteGradeLevel,
    onAddGradeLevel,
    onClose,
    onSubmit,
    studentManagement,
}: ClassFormDialogProps) {
    const { t } = useTranslation()

    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen && !isBusy) onClose()
            }}
            title={t(editingClass ? "edit-class" : "create-class")}
            description={t("create-class-help")}
            size={editingClass ? "xl" : "md"}
        >
            <form onSubmit={onSubmit}>
                <FieldGroup>
                    <div className="grid items-start gap-4 md:grid-cols-2">
                        <GradeLevelField
                            id="class-grade"
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
                        <Field>
                            <FieldLabel htmlFor="class-name">
                                {t("class-name")}
                            </FieldLabel>
                            <Input
                                id="class-name"
                                list="existing-class-names"
                                value={className}
                                onChange={(event) =>
                                    onClassNameChange(event.target.value)
                                }
                                placeholder={t("class-name-placeholder")}
                                maxLength={120}
                                required
                            />
                            <datalist id="existing-class-names">
                                {classes.map((studentClass) => (
                                    <option
                                        key={studentClass.id}
                                        value={studentClass.name}
                                        label={formatClassName(
                                            studentClass.grade_level,
                                            studentClass.name
                                        )}
                                    />
                                ))}
                            </datalist>
                        </Field>
                    </div>
                    {editingClass && studentManagement}
                    {error && <FieldError>{error}</FieldError>}
                    <DialogFormActions
                        isBusy={isBusy}
                        isEditing={Boolean(editingClass)}
                        submitLabel={t(
                            editingClass ? "save-class" : "create-class"
                        )}
                        onClose={onClose}
                    />
                </FieldGroup>
            </form>
        </Dialog>
    )
}

import type { GradeLevel, StudentClass } from "@/api/types"
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
import { formatClassName } from "@/lib/utils"
import { type FormEvent, type ReactNode, useState } from "react"
import { useTranslation } from "react-i18next"

type ClassFormDialogProps = {
    editingClass: StudentClass | null
    classes: StudentClass[]
    gradeLevels: GradeLevel[]
    isBusy: boolean
    error: string | null
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    /** Creates a grade level; null when it failed (the error is shown). */
    onAddGradeLevel: (name: string) => Promise<GradeLevel | null>
    onClose: () => void
    onSubmit: (values: { name: string; gradeLevel: string }) => void
    studentManagement?: ReactNode
}

/**
 * Creates a class, or edits one with its students. Mount it while it is
 * open, keyed by the class, so each opening starts from that class.
 */
export function ClassFormDialog({
    editingClass,
    classes,
    gradeLevels,
    isBusy,
    error,
    onDeleteGradeLevel,
    onAddGradeLevel,
    onClose,
    onSubmit,
    studentManagement,
}: ClassFormDialogProps) {
    const { t } = useTranslation()
    const [className, setClassName] = useState(editingClass?.name ?? "")
    const [gradeLevel, setGradeLevel] = useState(
        editingClass?.grade_level ?? ""
    )
    const [newGradeLevel, setNewGradeLevel] = useState("")
    const [isAddingGradeLevel, setIsAddingGradeLevel] = useState(false)

    async function addGradeLevel() {
        if (!newGradeLevel.trim()) return
        const created = await onAddGradeLevel(newGradeLevel.trim())
        if (!created) return
        setGradeLevel(created.name)
        setNewGradeLevel("")
        setIsAddingGradeLevel(false)
    }

    function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        onSubmit({ name: className.trim(), gradeLevel })
    }

    return (
        <Dialog
            open
            onOpenChange={(nextOpen) => {
                if (!nextOpen && !isBusy) onClose()
            }}
            title={t(editingClass ? "edit-class" : "create-class")}
            description={t("create-class-help")}
            size={editingClass ? "xl" : "md"}
        >
            <FieldGroup>
                <form id="class-form" onSubmit={submit}>
                    <div className="grid items-start gap-4 md:grid-cols-2">
                        <GradeLevelField
                            id="class-grade"
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
                        <Field>
                            <FieldLabel htmlFor="class-name">
                                {t("class-name")}
                            </FieldLabel>
                            <Input
                                id="class-name"
                                list="existing-class-names"
                                value={className}
                                onChange={(event) =>
                                    setClassName(event.target.value)
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
                </form>
                {/* Outside the form: Enter in these inputs must not save it. */}
                {editingClass && studentManagement}
                {error && <FieldError>{error}</FieldError>}
                <DialogFormActions
                    form="class-form"
                    isBusy={isBusy}
                    isEditing={Boolean(editingClass)}
                    submitLabel={t(
                        editingClass ? "save-class" : "create-class"
                    )}
                    onClose={onClose}
                />
            </FieldGroup>
        </Dialog>
    )
}

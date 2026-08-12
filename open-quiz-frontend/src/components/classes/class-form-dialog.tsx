import type { GradeLevel, StudentClass } from "@/api/types"
import { GradeLevelSelect } from "@/components/grade-level-select"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { formatClassName } from "@/lib/utils"
import { LoaderCircle, Pencil, Plus } from "lucide-react"
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
                        <Field>
                            <FieldLabel htmlFor="class-grade">
                                {t("grade-level")}
                            </FieldLabel>
                            <div className="flex gap-2">
                                <GradeLevelSelect
                                    id="class-grade"
                                    value={gradeLevel}
                                    levels={gradeLevels}
                                    onChange={onGradeLevelChange}
                                    onDelete={onDeleteGradeLevel}
                                    disabled={isBusy}
                                />
                                <Button
                                    type="button"
                                    size="icon"
                                    variant="outline"
                                    aria-label={t("add-grade-level")}
                                    onClick={() =>
                                        onAddingGradeLevelChange(
                                            !isAddingGradeLevel
                                        )
                                    }
                                >
                                    <Plus />
                                </Button>
                            </div>
                            {isAddingGradeLevel && (
                                <div className="mt-2 flex gap-2">
                                    <Input
                                        value={newGradeLevel}
                                        onChange={(event) =>
                                            onNewGradeLevelChange(
                                                event.target.value
                                            )
                                        }
                                        onKeyDown={(event) => {
                                            if (event.key === "Enter") {
                                                event.preventDefault()
                                                onAddGradeLevel()
                                            }
                                        }}
                                        maxLength={80}
                                        placeholder={t(
                                            "grade-level-placeholder"
                                        )}
                                    />
                                    <Button
                                        type="button"
                                        size="sm"
                                        onClick={onAddGradeLevel}
                                    >
                                        {t("save-grade-level")}
                                    </Button>
                                </div>
                            )}
                        </Field>
                    </div>
                    {editingClass && studentManagement}
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
                        <Button type="submit" disabled={isBusy}>
                            {isBusy ? (
                                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                            ) : editingClass ? (
                                <Pencil />
                            ) : (
                                <Plus />
                            )}
                            {t(editingClass ? "save-class" : "create-class")}
                        </Button>
                    </div>
                </FieldGroup>
            </form>
        </Dialog>
    )
}

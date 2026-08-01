import type { Student, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { LoaderCircle, UserPlus } from "lucide-react"
import type { FormEvent } from "react"
import { useTranslation } from "react-i18next"

type StudentFormDialogProps = {
    studentClass: StudentClass | null
    availableClasses: StudentClass[]
    editingStudent: Student | null
    destinationClassId: number | null
    firstName: string
    lastName: string
    isBusy: boolean
    error: string | null
    onFirstNameChange: (value: string) => void
    onLastNameChange: (value: string) => void
    onDestinationClassChange: (classId: number) => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function StudentFormDialog({
    studentClass,
    availableClasses,
    editingStudent,
    destinationClassId,
    firstName,
    lastName,
    isBusy,
    error,
    onFirstNameChange,
    onLastNameChange,
    onDestinationClassChange,
    onClose,
    onSubmit,
}: StudentFormDialogProps) {
    const { t } = useTranslation()

    return (
        <Dialog
            open={studentClass !== null}
            onOpenChange={(open) => {
                if (!open && !isBusy) onClose()
            }}
            title={t(editingStudent ? "edit-student" : "add-student")}
            description={studentClass?.name}
            className="max-w-lg"
        >
            <form onSubmit={onSubmit}>
                <FieldGroup>
                    <Field>
                        <FieldLabel htmlFor="student-first-name">
                            {t("first-name")}
                        </FieldLabel>
                        <Input
                            id="student-first-name"
                            value={firstName}
                            onChange={(event) =>
                                onFirstNameChange(event.target.value)
                            }
                            maxLength={120}
                            required
                        />
                    </Field>
                    {editingStudent && destinationClassId !== null && (
                        <Field>
                            <FieldLabel htmlFor="student-class">
                                {t("student-class")}
                            </FieldLabel>
                            <select
                                id="student-class"
                                className="h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                                value={destinationClassId}
                                onChange={(event) =>
                                    onDestinationClassChange(
                                        Number(event.target.value)
                                    )
                                }
                            >
                                {availableClasses.map((availableClass) => (
                                    <option
                                        key={availableClass.id}
                                        value={availableClass.id}
                                    >
                                        {availableClass.name} —{" "}
                                        {availableClass.grade_level}
                                    </option>
                                ))}
                            </select>
                            <p className="text-xs text-muted-foreground">
                                {t("student-class-help")}
                            </p>
                        </Field>
                    )}
                    <Field>
                        <FieldLabel htmlFor="student-last-name">
                            {t("last-name")}
                        </FieldLabel>
                        <Input
                            id="student-last-name"
                            value={lastName}
                            onChange={(event) =>
                                onLastNameChange(event.target.value)
                            }
                            maxLength={120}
                            required
                        />
                        <p className="text-xs text-muted-foreground">
                            {t("student-id-generated-help")}
                        </p>
                    </Field>
                    {error && <FieldError>{error}</FieldError>}
                    <div className="flex justify-end gap-2">
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
                                <LoaderCircle className="animate-spin" />
                            ) : (
                                <UserPlus />
                            )}
                            {t(editingStudent ? "save-student" : "add-student")}
                        </Button>
                    </div>
                </FieldGroup>
            </form>
        </Dialog>
    )
}

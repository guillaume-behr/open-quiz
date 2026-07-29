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
    editingStudent: Student | null
    firstName: string
    lastName: string
    isBusy: boolean
    error: string | null
    onFirstNameChange: (value: string) => void
    onLastNameChange: (value: string) => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function StudentFormDialog({
    studentClass,
    editingStudent,
    firstName,
    lastName,
    isBusy,
    error,
    onFirstNameChange,
    onLastNameChange,
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

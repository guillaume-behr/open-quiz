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
import { LoaderCircle, Upload } from "lucide-react"
import type { FormEvent, RefObject } from "react"
import { useTranslation } from "react-i18next"

export function ImportStudentsDialog({
    studentClass,
    file,
    inputRef,
    isBusy,
    error,
    onFileChange,
    onClose,
    onSubmit,
}: {
    studentClass: StudentClass | null
    file: File | null
    inputRef: RefObject<HTMLInputElement | null>
    isBusy: boolean
    error: string | null
    onFileChange: (file: File | null) => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={studentClass !== null}
            onOpenChange={(open) => {
                if (!open && !isBusy) onClose()
            }}
            title={t("import-students")}
            description={t("import-students-help", {
                className: studentClass?.name,
            })}
            className="max-w-lg"
        >
            <form onSubmit={onSubmit}>
                <FieldGroup>
                    <Field>
                        <FieldLabel htmlFor="students-import-file">
                            {t("json-file")}
                        </FieldLabel>
                        <Input
                            ref={inputRef}
                            id="students-import-file"
                            type="file"
                            accept="application/json,.json"
                            onChange={(event) =>
                                onFileChange(event.target.files?.[0] ?? null)
                            }
                            required
                        />
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
                        <Button type="submit" disabled={isBusy || !file}>
                            {isBusy ? (
                                <LoaderCircle className="animate-spin" />
                            ) : (
                                <Upload />
                            )}
                            {t(isBusy ? "importing-json" : "import-students")}
                        </Button>
                    </div>
                </FieldGroup>
            </form>
        </Dialog>
    )
}

export function DeleteClassMemberDialog({
    studentClass,
    student,
    isBusy,
    error,
    onClose,
    onConfirm,
}: {
    studentClass: StudentClass | null
    student: Student | null
    isBusy: boolean
    error: string | null
    onClose: () => void
    onConfirm: () => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={studentClass !== null || student !== null}
            onOpenChange={(open) => {
                if (!open && !isBusy) onClose()
            }}
            title={t(studentClass ? "delete-class" : "delete-student")}
            description={t(
                studentClass ? "delete-class-help" : "delete-student-help",
                { name: studentClass?.name ?? student?.display_name ?? "" }
            )}
            className="max-w-md"
        >
            {error && <FieldError>{error}</FieldError>}
            <div className="mt-4 flex justify-end gap-2">
                <Button
                    type="button"
                    variant="outline"
                    disabled={isBusy}
                    onClick={onClose}
                >
                    {t("cancel")}
                </Button>
                <Button
                    type="button"
                    variant="destructive"
                    disabled={isBusy}
                    onClick={onConfirm}
                >
                    {isBusy && <LoaderCircle className="animate-spin" />}
                    {t("delete")}
                </Button>
            </div>
        </Dialog>
    )
}

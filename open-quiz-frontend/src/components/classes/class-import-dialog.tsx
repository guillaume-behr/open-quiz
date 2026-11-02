import { importStudentClasses } from "@/api/classes"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Field, FieldError, FieldLabel } from "@/components/ui/field"
import { apiErrorMessage } from "@/lib/errors"
import { LoaderCircle, Upload } from "lucide-react"
import { useRef, useState } from "react"
import { useTranslation } from "react-i18next"

type ClassImport = {
    classes: {
        name: string
        grade_level: string
        students: { identifier: string; display_name: string }[]
    }[]
}

export function ClassImportDialog({
    open,
    onOpenChange,
    onImported,
}: {
    open: boolean
    onOpenChange: (open: boolean) => void
    onImported: () => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={open}
            onOpenChange={onOpenChange}
            title={t("classes-import")}
            description={t("classes-import-help")}
        >
            <ClassImportForm
                onCancel={() => onOpenChange(false)}
                onImported={onImported}
            />
        </Dialog>
    )
}

/** Mounted while the dialog is open, so each opening starts from scratch. */
function ClassImportForm({
    onCancel,
    onImported,
}: {
    onCancel: () => void
    onImported: () => void
}) {
    const { t } = useTranslation()
    const [importPayload, setImportPayload] = useState<ClassImport | null>(null)
    const [importError, setImportError] = useState<string | null>(null)
    const [importFileName, setImportFileName] = useState("")
    const [isBusy, setIsBusy] = useState(false)
    const importInputRef = useRef<HTMLInputElement>(null)

    async function readImportFile(file: File) {
        setImportError(null)
        setImportPayload(null)
        try {
            if (!file.name.toLowerCase().endsWith(".json")) throw new Error()
            const parsed: unknown = JSON.parse(await file.text())
            if (
                !parsed ||
                typeof parsed !== "object" ||
                !Array.isArray((parsed as { classes?: unknown }).classes)
            )
                throw new Error()
            const value = parsed as typeof importPayload
            if (
                !value ||
                value.classes.length === 0 ||
                value.classes.some(
                    (item) =>
                        !item ||
                        typeof item.name !== "string" ||
                        typeof item.grade_level !== "string" ||
                        !Array.isArray(item.students) ||
                        item.students.some(
                            (student) =>
                                !student ||
                                typeof student.identifier !== "string" ||
                                typeof student.display_name !== "string"
                        )
                )
            )
                throw new Error()
            const identifiers = value.classes.flatMap((item) =>
                item.students.map((student) =>
                    student.identifier.trim().toLowerCase()
                )
            )
            if (new Set(identifiers).size !== identifiers.length)
                throw new Error()
            setImportPayload(value)
        } catch {
            setImportError(t("classes-import-invalid"))
        }
    }

    async function confirmImport() {
        if (!importPayload) return
        setIsBusy(true)
        setImportError(null)
        try {
            await importStudentClasses(importPayload)
            onImported()
        } catch (caught) {
            setImportError(
                apiErrorMessage(caught, t, t("classes-import-conflict"))
            )
        } finally {
            setIsBusy(false)
        }
    }

    return (
        <>
            <Field>
                <FieldLabel htmlFor="classes-import-file">
                    {t("classes-import-file")}
                </FieldLabel>
                <input
                    ref={importInputRef}
                    id="classes-import-file"
                    type="file"
                    className="sr-only"
                    accept="application/json,.json"
                    onChange={(event) => {
                        const file = event.target.files?.[0]
                        if (file) {
                            setImportFileName(file.name)
                            void readImportFile(file)
                        }
                    }}
                />
                <Button
                    type="button"
                    variant="outline"
                    disabled={isBusy}
                    onClick={() => importInputRef.current?.click()}
                >
                    <Upload />
                    {t("choose-json-file")}
                </Button>
                {importFileName && (
                    <p className="text-sm break-all text-muted-foreground">
                        {importFileName}
                    </p>
                )}
            </Field>
            {importPayload && (
                <div className="mt-4 rounded-lg border p-3 text-sm">
                    <p className="font-semibold">
                        {t("classes-import-preview")}
                    </p>
                    <p>
                        {t("classes-import-summary", {
                            classes: importPayload.classes.length,
                            students: importPayload.classes.reduce(
                                (sum, item) => sum + item.students.length,
                                0
                            ),
                        })}
                    </p>
                </div>
            )}
            {importError && (
                <FieldError className="mt-3">{importError}</FieldError>
            )}
            <div className="mt-5 flex justify-end gap-2">
                <Button type="button" variant="outline" onClick={onCancel}>
                    {t("cancel")}
                </Button>
                <Button
                    type="button"
                    disabled={!importPayload || isBusy}
                    onClick={() => void confirmImport()}
                >
                    {isBusy && <LoaderCircle className="animate-spin" />}
                    {t("import")}
                </Button>
            </div>
        </>
    )
}

import { downloadQuizResults, getAllQuizzes } from "@/api/quizzes"
import type { StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { useAsyncAction } from "@/hooks/use-async-action"
import { useResource } from "@/hooks/use-resource"
import { apiErrorMessage } from "@/lib/errors"
import { formatClassName, saveBlob } from "@/lib/utils"
import { Download, LoaderCircle } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

type ExportProps = {
    classes: StudentClass[]
    areClassesLoading: boolean
    classesFailed: boolean
}

export function ResultsExportDialog({
    open,
    onOpenChange,
    ...props
}: ExportProps & {
    open: boolean
    onOpenChange: (open: boolean) => void
}) {
    const { t } = useTranslation()
    const [isExporting, setIsExporting] = useState(false)
    return (
        <Dialog
            open={open}
            onOpenChange={(isOpen) => {
                if (!isExporting) onOpenChange(isOpen)
            }}
            title={t("export-results-csv")}
            description={t("export-results-help")}
            size="md"
        >
            <ResultsExportForm
                {...props}
                onExportingChange={setIsExporting}
                onCancel={() => onOpenChange(false)}
                onExported={() => onOpenChange(false)}
            />
        </Dialog>
    )
}

/** Mounted while the dialog is open: the quiz list loads at each opening. */
function ResultsExportForm({
    classes,
    areClassesLoading,
    classesFailed,
    onExportingChange,
    onCancel,
    onExported,
}: ExportProps & {
    onExportingChange: (isExporting: boolean) => void
    onCancel: () => void
    onExported: () => void
}) {
    const { t } = useTranslation()
    const quizList = useResource(getAllQuizzes)
    const [exportClassId, setExportClassId] = useState<number | null>(null)
    const [exportQuizId, setExportQuizId] = useState<number | null>(null)
    const classId = exportClassId ?? classes[0]?.id ?? null
    const exporting = useAsyncAction(
        async () => {
            if (classId === null) return
            onExportingChange(true)
            try {
                saveBlob(
                    await downloadQuizResults(classId, exportQuizId),
                    `resultats-classe-${classId}${exportQuizId === null ? "-tous-les-quiz" : `-quiz-${exportQuizId}`}.csv`
                )
            } finally {
                onExportingChange(false)
            }
            onExported()
        },
        (caught) => apiErrorMessage(caught, t, t("export-results-error"))
    )
    const error =
        exporting.error ??
        (classesFailed || quizList.error ? t("export-results-error") : null)

    return (
        <>
            {quizList.isLoading || areClassesLoading ? (
                <div
                    className="flex min-h-32 items-center justify-center"
                    role="status"
                    aria-label={t("page-loading")}
                >
                    <LoaderCircle
                        className="size-7 animate-spin text-primary motion-reduce:animate-none"
                        aria-hidden="true"
                    />
                </div>
            ) : (
                <FieldGroup>
                    <div className="grid items-start gap-4 sm:grid-cols-2">
                        <Field>
                            <FieldLabel htmlFor="export-results-class">
                                {t("class-name")}
                            </FieldLabel>
                            <select
                                id="export-results-class"
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={classId ?? ""}
                                onChange={(event) =>
                                    setExportClassId(Number(event.target.value))
                                }
                            >
                                {classes.map((studentClass) => (
                                    <option
                                        key={studentClass.id}
                                        value={studentClass.id}
                                    >
                                        {formatClassName(
                                            studentClass.grade_level,
                                            studentClass.name
                                        )}
                                    </option>
                                ))}
                            </select>
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="export-results-quiz">
                                {t("quiz-title")}
                            </FieldLabel>
                            <select
                                id="export-results-quiz"
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={exportQuizId ?? ""}
                                onChange={(event) =>
                                    setExportQuizId(
                                        event.target.value
                                            ? Number(event.target.value)
                                            : null
                                    )
                                }
                            >
                                <option value="">{t("all-quizzes")}</option>
                                {(quizList.data ?? []).map((quiz) => (
                                    <option key={quiz.id} value={quiz.id}>
                                        {quiz.title}
                                    </option>
                                ))}
                            </select>
                        </Field>
                    </div>
                    {classes.length === 0 && !error && (
                        <p className="text-sm text-muted-foreground">
                            {t("export-results-no-classes")}
                        </p>
                    )}
                    {error && (
                        <p className="text-sm text-destructive" role="alert">
                            {error}
                        </p>
                    )}
                    <div className="flex justify-end gap-2">
                        <Button
                            type="button"
                            variant="outline"
                            disabled={exporting.isPending}
                            onClick={onCancel}
                        >
                            {t("cancel")}
                        </Button>
                        <Button
                            type="button"
                            disabled={exporting.isPending || classId === null}
                            onClick={() => void exporting.run()}
                        >
                            {exporting.isPending ? (
                                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                            ) : (
                                <Download />
                            )}
                            {t("export-csv")}
                        </Button>
                    </div>
                </FieldGroup>
            )}
        </>
    )
}

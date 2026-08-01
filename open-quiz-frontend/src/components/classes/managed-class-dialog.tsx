import type { Student, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Download, Pencil, Trash2, Upload, UserPlus } from "lucide-react"
import { useTranslation } from "react-i18next"

type ManagedClassDialogProps = {
    studentClass: StudentClass | null
    isBatchBusy: boolean
    batchError: string | null
    isImportOpen: boolean
    onClose: () => void
    onAddStudent: (studentClass: StudentClass) => void
    onImport: (studentClass: StudentClass) => void
    onExport: (studentClass: StudentClass) => void
    onEditStudent: (studentClass: StudentClass, student: Student) => void
    onDeleteStudent: (student: Student) => void
}

export function ManagedClassDialog({
    studentClass,
    isBatchBusy,
    batchError,
    isImportOpen,
    onClose,
    onAddStudent,
    onImport,
    onExport,
    onEditStudent,
    onDeleteStudent,
}: ManagedClassDialogProps) {
    const { t } = useTranslation()

    return (
        <Dialog
            open={studentClass !== null}
            onOpenChange={(open) => {
                if (!open) onClose()
            }}
            title={studentClass?.name ?? ""}
            description={
                studentClass
                    ? `${studentClass.grade_level} — ${t("student-count", {
                          count: studentClass.student_count,
                      })}`
                    : undefined
            }
            className="max-w-2xl"
        >
            {studentClass && (
                <div>
                    <div className="grid gap-2 sm:flex sm:flex-wrap sm:justify-end">
                        <Button
                            type="button"
                            onClick={() => onAddStudent(studentClass)}
                        >
                            <UserPlus />
                            {t("add-student")}
                        </Button>
                        <Button
                            type="button"
                            variant="outline"
                            disabled={isBatchBusy}
                            onClick={() => onImport(studentClass)}
                        >
                            <Upload />
                            {t("import-students")}
                        </Button>
                        <Button
                            type="button"
                            variant="outline"
                            disabled={isBatchBusy}
                            onClick={() => onExport(studentClass)}
                        >
                            <Download />
                            {t("export-students")}
                        </Button>
                    </div>
                    {batchError && !isImportOpen && (
                        <p className="mt-3 text-sm text-destructive">
                            {batchError}
                        </p>
                    )}
                    {studentClass.students.length === 0 ? (
                        <p className="mt-5 rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                            {t("no-student")}
                        </p>
                    ) : (
                        <ul className="mt-5 divide-y rounded-lg border">
                            {studentClass.students.map((student) => (
                                <li
                                    key={student.id}
                                    className="flex items-center justify-between gap-3 px-4 py-3"
                                >
                                    <div className="min-w-0">
                                        <p className="font-medium">
                                            {student.display_name}
                                        </p>
                                        <p className="text-xs text-muted-foreground">
                                            {student.identifier}
                                        </p>
                                    </div>
                                    <div className="flex gap-1">
                                        <Button
                                            type="button"
                                            size="icon"
                                            variant="ghost"
                                            aria-label={t("edit-student")}
                                            onClick={() =>
                                                onEditStudent(
                                                    studentClass,
                                                    student
                                                )
                                            }
                                        >
                                            <Pencil />
                                        </Button>
                                        <Button
                                            type="button"
                                            size="icon"
                                            variant="ghost"
                                            aria-label={t("delete-student")}
                                            onClick={() =>
                                                onDeleteStudent(student)
                                            }
                                        >
                                            <Trash2 />
                                        </Button>
                                    </div>
                                </li>
                            ))}
                        </ul>
                    )}
                </div>
            )}
        </Dialog>
    )
}

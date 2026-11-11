import {
    assignStudentAccount,
    createStudentClass,
    deleteStudentClass,
    downloadClassImportExample,
    getStudentClasses,
    unassignStudentAccount,
    updateStudentClass,
} from "@/api/classes"
import {
    createStudentAccount,
    getAllStudents,
    getClassStudentCredentials,
} from "@/api/students"
import type { GradeLevel, StudentAccount, StudentClass } from "@/api/types"
import { ClassCard, ClassFilters } from "@/components/classes/class-card"
import { ClassStudentsSection } from "@/components/classes/class-students-section"
import { ClassFormDialog } from "@/components/classes/class-form-dialog"
import { ClassImportDialog } from "@/components/classes/class-import-dialog"
import { writeCredentialCards } from "@/components/classes/print-credentials"
import { StudentAssignmentDialog } from "@/components/classes/student-assignment-dialog"
import { useAsyncAction } from "@/hooks/use-async-action"
import { usePagedList } from "@/hooks/use-paged-list"
import { Button } from "@/components/ui/button"
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog"
import { FieldError } from "@/components/ui/field"
import { saveBlob } from "@/lib/utils"
import { Pagination } from "@/components/ui/pagination"
import { FileJson, LoaderCircle, UsersRound, Upload } from "lucide-react"
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"
import { apiErrorMessage } from "@/lib/errors"

function loadClasses(
    page: number,
    filters: { search: string; gradeLevel: string }
) {
    return getStudentClasses(page, filters.search.trim(), filters.gradeLevel)
}

export function ClassesPanel({
    gradeLevels,
    onCreateGradeLevel,
    onDeleteGradeLevel,
    isCreateDialogOpen,
    onCreateDialogOpenChange,
}: {
    gradeLevels: GradeLevel[]
    onCreateGradeLevel: (name: string) => Promise<GradeLevel>
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
}) {
    const { t, i18n } = useTranslation()
    const classList = usePagedList(loadClasses, {
        search: "",
        gradeLevel: "",
    })
    const classes = classList.items
    const isLoading = !classList.hasSettled
    const loadError = classList.error ? t("classes-load-error") : null
    const [editing, setEditing] = useState<StudentClass | null>(null)
    const [managed, setManaged] = useState<StudentClass | null>(null)
    const [deleting, setDeleting] = useState<StudentClass | null>(null)
    const [assigning, setAssigning] = useState(false)
    const [accounts, setAccounts] = useState<StudentAccount[]>([])
    const [className, setClassName] = useState("")
    const [gradeLevel, setGradeLevel] = useState("")
    const [newGradeLevel, setNewGradeLevel] = useState("")
    const [isAddingGradeLevel, setIsAddingGradeLevel] = useState(false)
    const [isFormBusy, setIsFormBusy] = useState(false)
    const [printingClassId, setPrintingClassId] = useState<number | null>(null)
    const [importOpen, setImportOpen] = useState(false)

    // Each surface keeps its own error and busy state: a failure shows where
    // its action was taken, and never in the next dialog opened.
    const download = useAsyncAction(
        async () =>
            saveBlob(
                await downloadClassImportExample(),
                "open-quiz-classes-example.json"
            ),
        () => t("json-download-error")
    )

    // Show the managed class as the list last loaded it.
    const [syncedList, setSyncedList] = useState(classList.data)
    if (classList.data !== syncedList) {
        setSyncedList(classList.data)
        const loaded = classList.data
        if (loaded) {
            setManaged((current) =>
                current
                    ? (loaded.items.find((item) => item.id === current.id) ??
                      current)
                    : null
            )
        }
    }

    /** Saves the class form; its error is also the form's other errors. */
    const classForm = useAsyncAction(
        async () => {
            if (editing)
                await updateStudentClass(
                    editing.id,
                    className.trim(),
                    gradeLevel
                )
            else await createStudentClass(className.trim(), gradeLevel)
            closeClassForm()
            classList.reload()
        },
        (caught) => apiErrorMessage(caught, t, t("class-create-error"))
    )
    const setFormError = classForm.setError

    function closeClassForm() {
        setEditing(null)
        setClassName("")
        setGradeLevel("")
        setNewGradeLevel("")
        setIsAddingGradeLevel(false)
        setManaged(null)
        setFormError(null)
        onCreateDialogOpenChange(false)
    }

    function saveClass(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        void classForm.run()
    }

    async function addGradeLevel() {
        if (!newGradeLevel.trim()) return
        try {
            const created = await onCreateGradeLevel(newGradeLevel.trim())
            setGradeLevel(created.name)
            setNewGradeLevel("")
            setIsAddingGradeLevel(false)
        } catch (caught) {
            setFormError(
                apiErrorMessage(caught, t, t("grade-level-create-error"))
            )
        }
    }

    const assignment = useAsyncAction(
        async (selectedAccountIds: Set<number>) => {
            if (!managed || selectedAccountIds.size === 0) return
            let updated = managed
            try {
                for (const accountId of selectedAccountIds) {
                    updated = await assignStudentAccount(managed.id, accountId)
                }
            } finally {
                // Show the students assigned before a failure too.
                setManaged(updated)
            }
            setAssigning(false)
            classList.reload()
        },
        (caught) => apiErrorMessage(caught, t, t("student-assignment-error"))
    )

    async function openAssignment() {
        setIsFormBusy(true)
        setFormError(null)
        try {
            const available = (await getAllStudents()).filter(
                (account) =>
                    account.is_active && account.class_id !== managed?.id
            )
            setAccounts(available)
            assignment.setError(null)
            setAssigning(true)
        } catch {
            setFormError(t("students-load-error"))
        } finally {
            setIsFormBusy(false)
        }
    }

    async function createAndAssignStudent(
        firstName: string,
        lastName: string
    ): Promise<boolean> {
        if (!managed) return false
        setIsFormBusy(true)
        setFormError(null)
        try {
            const account = await createStudentAccount({
                first_name: firstName,
                last_name: lastName,
            })
            const updated = await assignStudentAccount(managed.id, account.id)
            setManaged(updated)
            setEditing(updated)
            classList.reload()
            return true
        } catch (caught) {
            setFormError(
                apiErrorMessage(caught, t, t("student-account-save-error"))
            )
            return false
        } finally {
            setIsFormBusy(false)
        }
    }

    async function unassign(accountId: number) {
        if (!managed) return
        setIsFormBusy(true)
        try {
            await unassignStudentAccount(managed.id, accountId)
            setManaged({
                ...managed,
                students: managed.students.filter(
                    (student) => student.account_id !== accountId
                ),
                student_count: Math.max(0, managed.student_count - 1),
            })
            classList.reload()
        } catch (caught) {
            setFormError(
                apiErrorMessage(caught, t, t("student-unassignment-error"))
            )
        } finally {
            setIsFormBusy(false)
        }
    }

    const deletion = useAsyncAction(
        async (studentClass: StudentClass) => {
            await deleteStudentClass(studentClass.id)
            setDeleting(null)
            classList.reload()
        },
        (caught) => apiErrorMessage(caught, t, t("class-student-delete-error"))
    )

    function openDeletion(studentClass: StudentClass | null) {
        deletion.setError(null)
        setDeleting(studentClass)
    }

    const printing = useAsyncAction(
        async (studentClass: StudentClass, printWindow: Window) => {
            setPrintingClassId(studentClass.id)
            try {
                const credentials = await getClassStudentCredentials(
                    studentClass.id
                )
                writeCredentialCards(
                    printWindow.document,
                    studentClass,
                    credentials,
                    t,
                    i18n.resolvedLanguage ?? "fr",
                    i18n.dir()
                )
                printWindow.onafterprint = () => printWindow.close()
                printWindow.focus()
                printWindow.setTimeout(() => printWindow.print(), 100)
            } catch (caught) {
                printWindow.close()
                throw caught
            } finally {
                setPrintingClassId(null)
            }
        },
        () => t("student-credentials-print-error")
    )

    function printCredentials(studentClass: StudentClass) {
        const printWindow = window.open("", "_blank")
        if (!printWindow) {
            printing.setError(t("student-credentials-print-popup-error"))
            return
        }
        printWindow.opener = null
        void printing.run(studentClass, printWindow)
    }

    const listError = printing.error ?? download.error

    return (
        <div className="mt-6">
            <div className="grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
                <ClassFilters
                    filters={classList.filters}
                    gradeLevels={gradeLevels}
                    onFilterChange={classList.setFilter}
                    onReset={classList.resetFilters}
                    onDeleteGradeLevel={onDeleteGradeLevel}
                />
                <div className="min-w-0">
                    <div className="mb-4 flex items-center justify-between gap-3">
                        <h3 className="font-semibold">{t("classes")}</h3>
                        <div className="flex flex-wrap gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => setImportOpen(true)}
                            >
                                <Upload />
                                {t("classes-import")}
                            </Button>
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => void download.run()}
                            >
                                <FileJson />
                                {t("download-json-example")}
                            </Button>
                        </div>
                    </div>
                    {isLoading ? (
                        <div
                            className="flex min-h-40 items-center justify-center"
                            role="status"
                            aria-label={t("page-loading")}
                        >
                            <LoaderCircle
                                className="size-7 animate-spin text-primary motion-reduce:animate-none"
                                aria-hidden="true"
                            />
                        </div>
                    ) : loadError ? (
                        <p
                            role="alert"
                            className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
                        >
                            {loadError}
                        </p>
                    ) : classes.length === 0 ? (
                        <div className="flex min-h-44 flex-col items-center justify-center rounded-xl border border-dashed text-center text-muted-foreground">
                            <UsersRound className="mb-2 size-8" />
                            <p>
                                {t(
                                    classList.filters.search ||
                                        classList.filters.gradeLevel
                                        ? "no-class-filtered"
                                        : "no-class"
                                )}
                            </p>
                        </div>
                    ) : (
                        <div
                            key={classes
                                .map((studentClass) => studentClass.id)
                                .join(",")}
                            className="grid animate-in gap-4 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none lg:grid-cols-2"
                        >
                            {classes.map((studentClass) => (
                                <ClassCard
                                    key={studentClass.id}
                                    studentClass={studentClass}
                                    isBusy={printingClassId === studentClass.id}
                                    onEdit={() => {
                                        setFormError(null)
                                        setEditing(studentClass)
                                        setManaged(studentClass)
                                        setClassName(studentClass.name)
                                        setGradeLevel(studentClass.grade_level)
                                    }}
                                    onDelete={() => openDeletion(studentClass)}
                                    onPrint={() =>
                                        printCredentials(studentClass)
                                    }
                                />
                            ))}
                        </div>
                    )}
                    {listError && (
                        <FieldError className="mt-4">{listError}</FieldError>
                    )}
                    <Pagination
                        currentPage={classList.page}
                        totalPages={classList.totalPages}
                        onPageChange={classList.showPage}
                    />
                </div>
            </div>

            <ClassImportDialog
                open={importOpen}
                onOpenChange={setImportOpen}
                onImported={() => {
                    setImportOpen(false)
                    classList.reload()
                    printing.setError(null)
                    download.setError(null)
                }}
            />
            <ClassFormDialog
                open={isCreateDialogOpen || editing !== null}
                editingClass={editing}
                classes={classes}
                gradeLevels={gradeLevels}
                className={className}
                gradeLevel={gradeLevel}
                newGradeLevel={newGradeLevel}
                isAddingGradeLevel={isAddingGradeLevel}
                isBusy={classForm.isPending || isFormBusy}
                error={classForm.error}
                onClassNameChange={setClassName}
                onGradeLevelChange={setGradeLevel}
                onNewGradeLevelChange={setNewGradeLevel}
                onAddingGradeLevelChange={setIsAddingGradeLevel}
                onDeleteGradeLevel={onDeleteGradeLevel}
                onAddGradeLevel={() => void addGradeLevel()}
                onClose={closeClassForm}
                onSubmit={saveClass}
                studentManagement={
                    managed ? (
                        <ClassStudentsSection
                            studentClass={managed}
                            isBusy={classForm.isPending || isFormBusy}
                            onOpenAssignment={() => void openAssignment()}
                            onCreateStudent={createAndAssignStudent}
                            onUnassign={(accountId) => void unassign(accountId)}
                        />
                    ) : undefined
                }
            />

            <StudentAssignmentDialog
                open={assigning}
                studentClass={managed}
                accounts={accounts}
                gradeLevels={gradeLevels}
                onDeleteGradeLevel={onDeleteGradeLevel}
                isBusy={assignment.isPending}
                error={assignment.error}
                onCancel={() => setAssigning(false)}
                onAssign={(accountIds) => void assignment.run(accountIds)}
            />

            <ConfirmDeleteDialog
                open={deleting !== null}
                title={t("delete-class")}
                description={t("delete-class-help", { name: deleting?.name })}
                isBusy={deletion.isPending}
                error={deletion.error}
                onClose={() => openDeletion(null)}
                onConfirm={() => deleting && void deletion.run(deleting)}
            />
        </div>
    )
}

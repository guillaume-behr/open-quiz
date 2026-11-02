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
import { ClassFormDialog } from "@/components/classes/class-form-dialog"
import { ClassImportDialog } from "@/components/classes/class-import-dialog"
import { writeCredentialCards } from "@/components/classes/print-credentials"
import { StudentAssignmentDialog } from "@/components/classes/student-assignment-dialog"
import { useResource } from "@/hooks/use-resource"
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
import { formatClassName, saveBlob } from "@/lib/utils"
import { Pagination } from "@/components/ui/pagination"
import {
    FileJson,
    LoaderCircle,
    Pencil,
    Printer,
    Trash2,
    UserMinus,
    UserPlus,
    UsersRound,
    Upload,
} from "lucide-react"
import { type FormEvent, useCallback, useState } from "react"
import { useTranslation } from "react-i18next"
import { apiErrorMessage } from "@/lib/errors"

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
    const [search, setSearch] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
    const [page, setPage] = useState(1)
    const classList = useResource(
        useCallback(
            () => getStudentClasses(page, search.trim(), gradeLevelFilter),
            [gradeLevelFilter, page, search]
        )
    )
    const classes = classList.data?.items ?? []
    const totalPages = classList.data?.totalPages ?? 1
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
    const [newStudentFirstName, setNewStudentFirstName] = useState("")
    const [newStudentLastName, setNewStudentLastName] = useState("")
    const [isBusy, setIsBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [importOpen, setImportOpen] = useState(false)

    async function downloadImportExample() {
        try {
            saveBlob(
                await downloadClassImportExample(),
                "open-quiz-classes-example.json"
            )
        } catch {
            setError(t("json-download-error"))
        }
    }

    // Show the managed class as the list last loaded it, and bring the page
    // back within range when a deletion shortened the list.
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
            if (loaded.page > loaded.totalPages) setPage(loaded.totalPages)
        }
    }

    function closeClassForm() {
        setEditing(null)
        setClassName("")
        setGradeLevel("")
        setNewGradeLevel("")
        setIsAddingGradeLevel(false)
        setManaged(null)
        setError(null)
        onCreateDialogOpenChange(false)
    }

    async function saveClass(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setIsBusy(true)
        setError(null)
        try {
            if (editing)
                await updateStudentClass(
                    editing.id,
                    className.trim(),
                    gradeLevel
                )
            else await createStudentClass(className.trim(), gradeLevel)
            closeClassForm()
            classList.reload()
        } catch (caught) {
            setError(apiErrorMessage(caught, t, t("class-create-error")))
        } finally {
            setIsBusy(false)
        }
    }

    async function addGradeLevel() {
        if (!newGradeLevel.trim()) return
        try {
            const created = await onCreateGradeLevel(newGradeLevel.trim())
            setGradeLevel(created.name)
            setNewGradeLevel("")
            setIsAddingGradeLevel(false)
        } catch (caught) {
            setError(apiErrorMessage(caught, t, t("grade-level-create-error")))
        }
    }

    async function openAssignment() {
        setIsBusy(true)
        setError(null)
        try {
            const available = (await getAllStudents()).filter(
                (account) =>
                    account.is_active && account.class_id !== managed?.id
            )
            setAccounts(available)
            setAssigning(true)
        } catch {
            setError(t("students-load-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function assign(selectedAccountIds: Set<number>) {
        if (!managed || selectedAccountIds.size === 0) return
        setIsBusy(true)
        setError(null)
        let updated = managed
        try {
            for (const accountId of selectedAccountIds) {
                updated = await assignStudentAccount(managed.id, accountId)
            }
            setManaged(updated)
            setAssigning(false)
            classList.reload()
        } catch (caught) {
            setManaged(updated)
            setError(apiErrorMessage(caught, t, t("student-assignment-error")))
        } finally {
            setIsBusy(false)
        }
    }

    async function createAndAssignStudent() {
        if (
            !managed ||
            !newStudentFirstName.trim() ||
            !newStudentLastName.trim()
        )
            return
        setIsBusy(true)
        setError(null)
        try {
            const account = await createStudentAccount({
                first_name: newStudentFirstName.trim(),
                last_name: newStudentLastName.trim(),
            })
            const updated = await assignStudentAccount(managed.id, account.id)
            setManaged(updated)
            setEditing(updated)
            setNewStudentFirstName("")
            setNewStudentLastName("")
            classList.reload()
        } catch (caught) {
            setError(
                apiErrorMessage(caught, t, t("student-account-save-error"))
            )
        } finally {
            setIsBusy(false)
        }
    }

    async function unassign(accountId: number) {
        if (!managed) return
        setIsBusy(true)
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
            setError(
                apiErrorMessage(caught, t, t("student-unassignment-error"))
            )
        } finally {
            setIsBusy(false)
        }
    }

    async function removeClass() {
        if (!deleting) return
        setIsBusy(true)
        try {
            await deleteStudentClass(deleting.id)
            setDeleting(null)
            classList.reload()
        } catch (caught) {
            setError(
                apiErrorMessage(caught, t, t("class-student-delete-error"))
            )
        } finally {
            setIsBusy(false)
        }
    }

    async function printCredentials(studentClass: StudentClass) {
        const printWindow = window.open("", "_blank")
        if (!printWindow) {
            setError(t("student-credentials-print-popup-error"))
            return
        }
        printWindow.opener = null
        setIsBusy(true)
        setError(null)
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
        } catch {
            printWindow.close()
            setError(t("student-credentials-print-error"))
        } finally {
            setIsBusy(false)
        }
    }

    return (
        <div className="mt-6">
            <div className="grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
                <aside className="h-fit rounded-xl border bg-background p-4">
                    <h3 className="font-semibold">{t("filters")}</h3>
                    <FieldGroup className="mt-4 gap-4">
                        <Field>
                            <FieldLabel htmlFor="class-filter-search">
                                {t("search")}
                            </FieldLabel>
                            <Input
                                id="class-filter-search"
                                value={search}
                                onChange={(event) => {
                                    setSearch(event.target.value)
                                    setPage(1)
                                }}
                                placeholder={t("search-class")}
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="class-filter-grade-level">
                                {t("grade-level")}
                            </FieldLabel>
                            <GradeLevelSelect
                                id="class-filter-grade-level"
                                value={gradeLevelFilter}
                                levels={gradeLevels}
                                onChange={(value) => {
                                    setGradeLevelFilter(value)
                                    setPage(1)
                                }}
                                onDelete={onDeleteGradeLevel}
                                required={false}
                                placeholder={t("all-grade-levels")}
                            />
                        </Field>
                        {(search || gradeLevelFilter) && (
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                    setSearch("")
                                    setGradeLevelFilter("")
                                    setPage(1)
                                }}
                            >
                                {t("clear-filters")}
                            </Button>
                        )}
                    </FieldGroup>
                </aside>
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
                                onClick={() => void downloadImportExample()}
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
                                    search || gradeLevelFilter
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
                                <article
                                    key={studentClass.id}
                                    className="relative rounded-xl border bg-background p-4"
                                >
                                    <Button
                                        type="button"
                                        size="icon-sm"
                                        variant="ghost"
                                        className="absolute end-12 top-4"
                                        onClick={() => {
                                            setEditing(studentClass)
                                            setManaged(studentClass)
                                            setClassName(studentClass.name)
                                            setGradeLevel(
                                                studentClass.grade_level
                                            )
                                        }}
                                        aria-label={t("edit-class")}
                                        title={t("edit-class")}
                                    >
                                        <Pencil />
                                    </Button>
                                    <Button
                                        type="button"
                                        size="icon-sm"
                                        variant="destructive"
                                        className="absolute end-4 top-4"
                                        onClick={() =>
                                            setDeleting(studentClass)
                                        }
                                        aria-label={t("delete-class")}
                                        title={t("delete-class")}
                                    >
                                        <Trash2 />
                                    </Button>
                                    <div className="flex items-start gap-3 pe-20">
                                        <div className="rounded-lg bg-primary/10 p-2 text-primary">
                                            <UsersRound className="size-5" />
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            <div className="mt-1 flex flex-wrap items-center gap-2">
                                                <p className="font-semibold break-words">
                                                    {formatClassName(
                                                        studentClass.grade_level,
                                                        studentClass.name
                                                    )}
                                                </p>
                                                <span className="rounded-full bg-primary/10 px-2.5 py-1 text-xs font-semibold whitespace-nowrap text-primary">
                                                    {t("student-count", {
                                                        count: studentClass.student_count,
                                                    })}
                                                </span>
                                            </div>
                                            <div className="mt-3 flex flex-wrap gap-2">
                                                <Button
                                                    type="button"
                                                    size="sm"
                                                    variant="outline"
                                                    onClick={() =>
                                                        void printCredentials(
                                                            studentClass
                                                        )
                                                    }
                                                    disabled={isBusy}
                                                >
                                                    <Printer />
                                                    {t(
                                                        "print-student-credentials"
                                                    )}
                                                </Button>
                                            </div>
                                        </div>
                                    </div>
                                </article>
                            ))}
                        </div>
                    )}
                    {error && <FieldError className="mt-4">{error}</FieldError>}
                    <Pagination
                        currentPage={page}
                        totalPages={totalPages}
                        onPageChange={setPage}
                    />
                </div>
            </div>

            <ClassImportDialog
                open={importOpen}
                onOpenChange={setImportOpen}
                onImported={() => {
                    setImportOpen(false)
                    classList.reload()
                    setError(null)
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
                isBusy={isBusy}
                error={error}
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
                        <section className="space-y-4 border-t pt-5">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                                <div>
                                    <h3 className="font-semibold">
                                        {t("manage-students")}
                                    </h3>
                                    <p className="text-xs text-muted-foreground">
                                        {t("student-count", {
                                            count: managed.student_count,
                                        })}
                                    </p>
                                </div>
                                <Button
                                    type="button"
                                    size="sm"
                                    variant="outline"
                                    onClick={() => void openAssignment()}
                                    disabled={isBusy}
                                >
                                    <UserPlus />
                                    {t("assign-student")}
                                </Button>
                            </div>
                            <div className="grid gap-2 rounded-lg border bg-muted/20 p-3 sm:grid-cols-[1fr_1fr_auto]">
                                <Input
                                    value={newStudentFirstName}
                                    onChange={(event) =>
                                        setNewStudentFirstName(
                                            event.target.value
                                        )
                                    }
                                    placeholder={t("first-name")}
                                    aria-label={t("first-name")}
                                />
                                <Input
                                    value={newStudentLastName}
                                    onChange={(event) =>
                                        setNewStudentLastName(
                                            event.target.value
                                        )
                                    }
                                    placeholder={t("last-name")}
                                    aria-label={t("last-name")}
                                />
                                <Button
                                    type="button"
                                    size="sm"
                                    onClick={() =>
                                        void createAndAssignStudent()
                                    }
                                    disabled={
                                        isBusy ||
                                        !newStudentFirstName.trim() ||
                                        !newStudentLastName.trim()
                                    }
                                >
                                    <UserPlus />
                                    {t("create-student-account")}
                                </Button>
                            </div>
                            {managed.students.length === 0 ? (
                                <p className="rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                                    {t("no-student")}
                                </p>
                            ) : (
                                <ul className="max-h-56 divide-y overflow-auto rounded-lg border bg-background">
                                    {managed.students.map((student) => (
                                        <li
                                            key={student.id}
                                            className="flex items-center justify-between gap-3 px-4 py-3"
                                        >
                                            <div>
                                                <p className="font-medium">
                                                    {student.display_name}
                                                </p>
                                                <p className="text-xs text-muted-foreground">
                                                    {student.identifier}
                                                </p>
                                            </div>
                                            {student.account_id !== null && (
                                                <Button
                                                    type="button"
                                                    size="icon-sm"
                                                    variant="ghost"
                                                    disabled={isBusy}
                                                    onClick={() =>
                                                        void unassign(
                                                            student.account_id!
                                                        )
                                                    }
                                                    aria-label={t(
                                                        "unassign-student"
                                                    )}
                                                >
                                                    <UserMinus />
                                                </Button>
                                            )}
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </section>
                    ) : undefined
                }
            />

            <StudentAssignmentDialog
                open={assigning}
                studentClass={managed}
                accounts={accounts}
                gradeLevels={gradeLevels}
                onDeleteGradeLevel={onDeleteGradeLevel}
                isBusy={isBusy}
                error={error}
                onCancel={() => setAssigning(false)}
                onAssign={(accountIds) => void assign(accountIds)}
            />

            <Dialog
                open={deleting !== null}
                onOpenChange={(open) => !open && setDeleting(null)}
                title={t("delete-class")}
                description={t("delete-class-help", { name: deleting?.name })}
                size="sm"
            >
                <div className="flex justify-end gap-2">
                    <Button variant="outline" onClick={() => setDeleting(null)}>
                        {t("cancel")}
                    </Button>
                    <Button
                        variant="destructive"
                        disabled={isBusy}
                        onClick={() => void removeClass()}
                    >
                        {isBusy && (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        )}
                        {t("delete")}
                    </Button>
                </div>
            </Dialog>
        </div>
    )
}

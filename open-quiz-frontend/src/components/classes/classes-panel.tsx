import {
    assignStudentAccount,
    createStudentClass,
    deleteStudentClass,
    getStudentClasses,
    unassignStudentAccount,
    updateStudentClass,
} from "@/api/classes"
import {
    createStudentAccount,
    getAllStudents,
    getStudentCredentials,
} from "@/api/students"
import type { GradeLevel, StudentAccount, StudentClass } from "@/api/types"
import { ClassFormDialog } from "@/components/classes/class-form-dialog"
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
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { Pagination } from "@/components/ui/pagination"
import {
    Check,
    LoaderCircle,
    Pencil,
    Printer,
    Trash2,
    UserMinus,
    UserPlus,
    UsersRound,
} from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

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
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [search, setSearch] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)
    const [reloadKey, setReloadKey] = useState(0)
    const [isLoading, setIsLoading] = useState(true)
    const [editing, setEditing] = useState<StudentClass | null>(null)
    const [managed, setManaged] = useState<StudentClass | null>(null)
    const [deleting, setDeleting] = useState<StudentClass | null>(null)
    const [assigning, setAssigning] = useState(false)
    const [accounts, setAccounts] = useState<StudentAccount[]>([])
    const [assignmentSearch, setAssignmentSearch] = useState("")
    const [assignmentClassFilter, setAssignmentClassFilter] = useState("")
    const [assignmentGradeLevelFilter, setAssignmentGradeLevelFilter] =
        useState("")
    const [selectedAccountIds, setSelectedAccountIds] = useState<Set<number>>(
        new Set()
    )
    const [className, setClassName] = useState("")
    const [gradeLevel, setGradeLevel] = useState("")
    const [newGradeLevel, setNewGradeLevel] = useState("")
    const [isAddingGradeLevel, setIsAddingGradeLevel] = useState(false)
    const [newStudentFirstName, setNewStudentFirstName] = useState("")
    const [newStudentLastName, setNewStudentLastName] = useState("")
    const [isBusy, setIsBusy] = useState(false)
    const [loadError, setLoadError] = useState<string | null>(null)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let active = true
        getStudentClasses(page, search.trim(), gradeLevelFilter)
            .then((result) => {
                if (!active) return
                setClasses(result.items)
                setTotalPages(result.totalPages)
                setManaged((current) =>
                    current
                        ? (result.items.find(
                              (item) => item.id === current.id
                          ) ?? current)
                        : null
                )
                setLoadError(null)
                if (result.page > result.totalPages) {
                    setPage(result.totalPages)
                }
            })
            .catch(() => active && setLoadError(t("classes-load-error")))
            .finally(() => active && setIsLoading(false))
        return () => {
            active = false
        }
    }, [gradeLevelFilter, page, reloadKey, search, t])

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
            setReloadKey((value) => value + 1)
        } catch {
            setError(t("class-create-error"))
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
        } catch {
            setError(t("grade-level-create-error"))
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
            setAssignmentSearch("")
            setAssignmentClassFilter("")
            setAssignmentGradeLevelFilter("")
            setSelectedAccountIds(new Set())
            setAssigning(true)
        } catch {
            setError(t("students-load-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function assign() {
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
            setSelectedAccountIds(new Set())
            setReloadKey((value) => value + 1)
        } catch {
            setManaged(updated)
            setError(t("student-assignment-error"))
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
            setReloadKey((value) => value + 1)
        } catch {
            setError(t("student-account-save-error"))
        } finally {
            setIsBusy(false)
        }
    }

    const normalizedAssignmentSearch = assignmentSearch
        .trim()
        .toLocaleLowerCase()
    const assignmentClasses = Array.from(
        new Map(
            accounts
                .filter(
                    (account) =>
                        account.class_id !== null && account.class_name !== null
                )
                .map(
                    (account) =>
                        [account.class_id!, account.class_name!] as const
                )
        ).entries()
    ).sort(([, firstName], [, secondName]) =>
        firstName.localeCompare(secondName, i18n.resolvedLanguage)
    )
    const filteredAccounts = accounts.filter((account) => {
        const matchesSearch = normalizedAssignmentSearch
            ? `${account.display_name} ${account.identifier} ${account.class_name ?? ""} ${account.grade_level ?? ""}`
                  .toLocaleLowerCase()
                  .includes(normalizedAssignmentSearch)
            : true
        const matchesClass =
            assignmentClassFilter === "unassigned"
                ? account.class_id === null
                : assignmentClassFilter
                  ? account.class_id === Number(assignmentClassFilter)
                  : true
        const matchesGradeLevel = assignmentGradeLevelFilter
            ? account.grade_level === assignmentGradeLevelFilter
            : true
        return matchesSearch && matchesClass && matchesGradeLevel
    })

    function toggleAccount(accountId: number) {
        setSelectedAccountIds((current) => {
            const next = new Set(current)
            if (next.has(accountId)) next.delete(accountId)
            else next.add(accountId)
            return next
        })
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
            setReloadKey((value) => value + 1)
        } catch {
            setError(t("student-unassignment-error"))
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
            setReloadKey((value) => value + 1)
        } catch {
            setError(t("class-student-delete-error"))
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
            const credentials = await getStudentCredentials(studentClass.id)
            const document = printWindow.document
            document.title = t("student-credentials-print-title", {
                className: studentClass.name,
            })
            document.documentElement.lang = i18n.resolvedLanguage ?? "fr"
            document.documentElement.dir = i18n.dir()
            const style = document.createElement("style")
            style.textContent = `
                @page { size: A4 portrait; margin: 7mm; }
                * { box-sizing: border-box; }
                body { margin: 0; color: #111; font-family: Arial, sans-serif; }
                main { display: grid; grid-template-columns: repeat(2, 1fr); }
                article { min-height: 39mm; padding: 5mm 6mm; border-right: 1px dashed #777; border-bottom: 1px dashed #777; break-inside: avoid; }
                article:nth-child(2n) { border-right: 0; }
                .class { margin: 0 0 2mm; color: #555; font-size: 9pt; }
                .name { margin: 0 0 3mm; font-size: 13pt; font-weight: 700; }
                dl { display: grid; grid-template-columns: auto 1fr; gap: 1.5mm 3mm; margin: 0; font-size: 10pt; }
                dt { color: #555; }
                dd { margin: 0; font-family: monospace; font-size: 11pt; font-weight: 700; overflow-wrap: anywhere; }
                .empty { grid-column: 1 / -1; padding: 10mm; text-align: center; }
            `
            document.head.append(style)
            const main = document.createElement("main")
            if (credentials.length === 0) {
                const empty = document.createElement("p")
                empty.className = "empty"
                empty.textContent = t("no-student-in-class")
                main.append(empty)
            }
            for (const credential of credentials) {
                const card = document.createElement("article")
                const classLabel = document.createElement("p")
                classLabel.className = "class"
                classLabel.textContent = studentClass.name
                const name = document.createElement("p")
                name.className = "name"
                name.textContent = credential.display_name
                const details = document.createElement("dl")
                for (const [label, value] of [
                    [t("student-id"), credential.identifier],
                    [
                        t("login-password"),
                        credential.password ?? t("password-unavailable"),
                    ],
                ]) {
                    const term = document.createElement("dt")
                    term.textContent = label
                    const description = document.createElement("dd")
                    description.textContent = value
                    details.append(term, description)
                }
                card.append(classLabel, name, details)
                main.append(card)
            }
            document.body.append(main)
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
                    <h3 className="mb-4 font-semibold">{t("classes")}</h3>
                    {isLoading ? (
                        <div
                            className="flex min-h-40 items-center justify-center"
                            role="status"
                            aria-label={t("page-loading")}
                        >
                            <LoaderCircle className="size-7 animate-spin text-primary motion-reduce:animate-none" />
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
                                        className="absolute top-4 right-12"
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
                                        className="absolute top-4 right-4"
                                        onClick={() =>
                                            setDeleting(studentClass)
                                        }
                                        aria-label={t("delete-class")}
                                        title={t("delete-class")}
                                    >
                                        <Trash2 />
                                    </Button>
                                    <div className="flex items-start gap-3 pr-20">
                                        <div className="rounded-lg bg-primary/10 p-2 text-primary">
                                            <UsersRound className="size-5" />
                                        </div>
                                        <div className="min-w-0 flex-1">
                                            <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                                                {studentClass.grade_level}
                                            </p>
                                            <div className="mt-1 flex flex-wrap items-center gap-2">
                                                <p className="font-semibold break-words">
                                                    {studentClass.name}
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

            <Dialog
                open={assigning}
                onOpenChange={(open) => !open && setAssigning(false)}
                title={t("assign-student")}
                description={t("assign-student-help", {
                    className: managed?.name,
                })}
                className="max-w-3xl"
            >
                {accounts.length === 0 ? (
                    <p className="rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                        {t("no-student-to-assign")}
                    </p>
                ) : (
                    <div className="space-y-4">
                        <div className="grid gap-3 sm:grid-cols-3">
                            <Field>
                                <FieldLabel htmlFor="assignment-student-search">
                                    {t("search")}
                                </FieldLabel>
                                <Input
                                    id="assignment-student-search"
                                    value={assignmentSearch}
                                    onChange={(event) =>
                                        setAssignmentSearch(event.target.value)
                                    }
                                    placeholder={t("search-student")}
                                />
                            </Field>
                            <Field>
                                <FieldLabel htmlFor="assignment-student-class">
                                    {t("student-class")}
                                </FieldLabel>
                                <select
                                    id="assignment-student-class"
                                    className={NATIVE_SELECT_CLASS_NAME}
                                    value={assignmentClassFilter}
                                    onChange={(event) =>
                                        setAssignmentClassFilter(
                                            event.target.value
                                        )
                                    }
                                >
                                    <option value="">{t("all-classes")}</option>
                                    <option value="unassigned">
                                        {t("student-unassigned")}
                                    </option>
                                    {assignmentClasses.map(
                                        ([classId, name]) => (
                                            <option
                                                key={classId}
                                                value={classId}
                                            >
                                                {name}
                                            </option>
                                        )
                                    )}
                                </select>
                            </Field>
                            <Field>
                                <FieldLabel htmlFor="assignment-student-grade-level">
                                    {t("grade-level")}
                                </FieldLabel>
                                <GradeLevelSelect
                                    id="assignment-student-grade-level"
                                    value={assignmentGradeLevelFilter}
                                    levels={gradeLevels}
                                    onChange={(value) =>
                                        setAssignmentGradeLevelFilter(value)
                                    }
                                    onDelete={onDeleteGradeLevel}
                                    required={false}
                                    placeholder={t("all-grade-levels")}
                                />
                            </Field>
                        </div>

                        <div className="flex flex-wrap items-center justify-between gap-2 text-sm">
                            <p className="text-muted-foreground">
                                {t("selected-students", {
                                    count: selectedAccountIds.size,
                                })}
                            </p>
                            {(assignmentSearch ||
                                assignmentClassFilter ||
                                assignmentGradeLevelFilter) && (
                                <Button
                                    type="button"
                                    size="sm"
                                    variant="ghost"
                                    onClick={() => {
                                        setAssignmentSearch("")
                                        setAssignmentClassFilter("")
                                        setAssignmentGradeLevelFilter("")
                                    }}
                                >
                                    {t("clear-filters")}
                                </Button>
                            )}
                        </div>

                        {filteredAccounts.length === 0 ? (
                            <p className="rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                                {t("no-student-matching-filters")}
                            </p>
                        ) : (
                            <div className="grid gap-3 sm:grid-cols-2">
                                {filteredAccounts.map((account) => {
                                    const isSelected = selectedAccountIds.has(
                                        account.id
                                    )
                                    return (
                                        <button
                                            key={account.id}
                                            type="button"
                                            aria-pressed={isSelected}
                                            onClick={() =>
                                                toggleAccount(account.id)
                                            }
                                            className={`relative rounded-xl border p-4 text-left transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none ${isSelected ? "border-primary bg-primary/5 ring-2 ring-primary/20" : "bg-background hover:border-primary/50 hover:bg-muted/40"}`}
                                        >
                                            <span
                                                className={`absolute top-4 right-4 flex size-6 items-center justify-center rounded-md border ${isSelected ? "border-primary bg-primary text-primary-foreground" : "text-transparent"}`}
                                                aria-hidden="true"
                                            >
                                                <Check className="size-4" />
                                            </span>
                                            <div className="pr-9">
                                                <p className="font-semibold break-words">
                                                    {account.display_name}
                                                </p>
                                                <p className="mt-1 text-xs text-muted-foreground">
                                                    {account.identifier}
                                                </p>
                                            </div>
                                            <div className="mt-4 grid grid-cols-2 gap-3 border-t pt-3 text-sm">
                                                <div className="min-w-0">
                                                    <p className="text-xs text-muted-foreground">
                                                        {t("student-class")}
                                                    </p>
                                                    <p className="mt-1 truncate font-medium">
                                                        {account.class_name ??
                                                            t(
                                                                "student-unassigned"
                                                            )}
                                                    </p>
                                                </div>
                                                <div className="min-w-0">
                                                    <p className="text-xs text-muted-foreground">
                                                        {t("grade-level")}
                                                    </p>
                                                    <p className="mt-1 truncate font-medium">
                                                        {account.grade_level ??
                                                            t(
                                                                "student-no-grade-level"
                                                            )}
                                                    </p>
                                                </div>
                                            </div>
                                        </button>
                                    )
                                })}
                            </div>
                        )}
                    </div>
                )}
                {error && <FieldError className="mt-4">{error}</FieldError>}
                <div className="mt-5 flex justify-end gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        onClick={() => setAssigning(false)}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        type="button"
                        onClick={() => void assign()}
                        disabled={isBusy || selectedAccountIds.size === 0}
                    >
                        {isBusy && (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        )}
                        {t("assign-selected-students", {
                            count: selectedAccountIds.size,
                        })}
                    </Button>
                </div>
            </Dialog>

            <Dialog
                open={deleting !== null}
                onOpenChange={(open) => !open && setDeleting(null)}
                title={t("delete-class")}
                description={t("delete-class-help", { name: deleting?.name })}
                className="max-w-md"
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

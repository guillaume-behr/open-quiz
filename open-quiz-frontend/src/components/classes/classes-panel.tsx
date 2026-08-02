import {
    assignStudentAccount,
    createStudentClass,
    deleteStudentClass,
    getStudentClasses,
    unassignStudentAccount,
    updateStudentClass,
} from "@/api/classes"
import { getAllStudents } from "@/api/students"
import type { GradeLevel, StudentAccount, StudentClass } from "@/api/types"
import { ClassFormDialog } from "@/components/classes/class-form-dialog"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Pagination } from "@/components/ui/pagination"
import {
    LoaderCircle,
    Pencil,
    Search,
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
    const { t } = useTranslation()
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [search, setSearch] = useState("")
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)
    const [reloadKey, setReloadKey] = useState(0)
    const [isLoading, setIsLoading] = useState(true)
    const [editing, setEditing] = useState<StudentClass | null>(null)
    const [managed, setManaged] = useState<StudentClass | null>(null)
    const [deleting, setDeleting] = useState<StudentClass | null>(null)
    const [assigning, setAssigning] = useState(false)
    const [accounts, setAccounts] = useState<StudentAccount[]>([])
    const [selectedAccountId, setSelectedAccountId] = useState<number | null>(
        null
    )
    const [className, setClassName] = useState("")
    const [gradeLevel, setGradeLevel] = useState("")
    const [newGradeLevel, setNewGradeLevel] = useState("")
    const [isAddingGradeLevel, setIsAddingGradeLevel] = useState(false)
    const [isBusy, setIsBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let active = true
        getStudentClasses(page, search.trim())
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
                setError(null)
            })
            .catch(() => active && setError(t("classes-load-error")))
            .finally(() => active && setIsLoading(false))
        return () => {
            active = false
        }
    }, [page, reloadKey, search, t])

    function closeClassForm() {
        setEditing(null)
        setClassName("")
        setGradeLevel("")
        setNewGradeLevel("")
        setIsAddingGradeLevel(false)
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
            setSelectedAccountId(available[0]?.id ?? null)
            setAssigning(true)
        } catch {
            setError(t("students-load-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function assign() {
        if (!managed || selectedAccountId === null) return
        setIsBusy(true)
        try {
            const updated = await assignStudentAccount(
                managed.id,
                selectedAccountId
            )
            setManaged(updated)
            setAssigning(false)
            setReloadKey((value) => value + 1)
        } catch {
            setError(t("student-assignment-error"))
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

    return (
        <div className="mt-6">
            <div className="relative mb-5 max-w-md">
                <Search className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input
                    className="pl-9"
                    aria-label={t("search-class")}
                    value={search}
                    onChange={(event) => {
                        setSearch(event.target.value)
                        setPage(1)
                    }}
                    placeholder={t("search-class")}
                />
            </div>
            {isLoading ? (
                <div className="flex min-h-40 items-center justify-center">
                    <LoaderCircle className="size-7 animate-spin text-primary" />
                </div>
            ) : classes.length === 0 ? (
                <div className="flex min-h-44 flex-col items-center justify-center rounded-xl border border-dashed text-muted-foreground">
                    <UsersRound className="mb-2 size-8" />
                    <p>{t("no-class")}</p>
                </div>
            ) : (
                <div className="grid gap-4 lg:grid-cols-2">
                    {classes.map((studentClass) => (
                        <article
                            key={studentClass.id}
                            className="rounded-xl border p-4"
                        >
                            <div className="flex items-start justify-between gap-3">
                                <button
                                    className="min-w-0 text-left"
                                    onClick={() => setManaged(studentClass)}
                                >
                                    <h3 className="truncate text-lg font-semibold">
                                        {studentClass.name}
                                    </h3>
                                    <p className="text-sm text-muted-foreground">
                                        {studentClass.grade_level} ·{" "}
                                        {t("student-count", {
                                            count: studentClass.student_count,
                                        })}
                                    </p>
                                </button>
                                <div className="flex gap-1">
                                    <Button
                                        size="icon"
                                        variant="ghost"
                                        onClick={() => {
                                            setEditing(studentClass)
                                            setClassName(studentClass.name)
                                            setGradeLevel(
                                                studentClass.grade_level
                                            )
                                        }}
                                        aria-label={t("edit-class")}
                                    >
                                        <Pencil />
                                    </Button>
                                    <Button
                                        size="icon"
                                        variant="ghost"
                                        onClick={() =>
                                            setDeleting(studentClass)
                                        }
                                        aria-label={t("delete-class")}
                                    >
                                        <Trash2 />
                                    </Button>
                                </div>
                            </div>
                            <Button
                                className="mt-4 w-full"
                                variant="outline"
                                onClick={() => setManaged(studentClass)}
                            >
                                {t("manage-students")}
                            </Button>
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
            />

            <Dialog
                open={managed !== null}
                onOpenChange={(open) => !open && setManaged(null)}
                title={managed?.name ?? ""}
                description={
                    managed
                        ? `${managed.grade_level} — ${t("student-count", { count: managed.student_count })}`
                        : undefined
                }
                className="max-w-2xl"
            >
                {managed && (
                    <div>
                        <div className="flex justify-end">
                            <Button
                                onClick={() => void openAssignment()}
                                disabled={isBusy}
                            >
                                <UserPlus />
                                {t("assign-student")}
                            </Button>
                        </div>
                        {managed.students.length === 0 ? (
                            <p className="mt-5 rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                                {t("no-student")}
                            </p>
                        ) : (
                            <ul className="mt-5 divide-y rounded-lg border">
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
                                                size="icon"
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
                    </div>
                )}
            </Dialog>

            <Dialog
                open={assigning}
                onOpenChange={(open) => !open && setAssigning(false)}
                title={t("assign-student")}
                description={t("assign-student-help", {
                    className: managed?.name,
                })}
                className="max-w-lg"
            >
                {accounts.length === 0 ? (
                    <p className="rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                        {t("no-student-to-assign")}
                    </p>
                ) : (
                    <select
                        className="h-10 w-full rounded-lg border bg-background px-3"
                        value={selectedAccountId ?? ""}
                        onChange={(event) =>
                            setSelectedAccountId(Number(event.target.value))
                        }
                    >
                        {accounts.map((account) => (
                            <option key={account.id} value={account.id}>
                                {account.display_name} ({account.identifier})
                                {account.class_name
                                    ? ` — ${account.class_name}`
                                    : ""}
                            </option>
                        ))}
                    </select>
                )}
                <div className="mt-5 flex justify-end gap-2">
                    <Button
                        variant="outline"
                        onClick={() => setAssigning(false)}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        onClick={() => void assign()}
                        disabled={isBusy || selectedAccountId === null}
                    >
                        {isBusy && <LoaderCircle className="animate-spin" />}
                        {t("assign")}
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
                        {isBusy && <LoaderCircle className="animate-spin" />}
                        {t("delete")}
                    </Button>
                </div>
            </Dialog>
        </div>
    )
}

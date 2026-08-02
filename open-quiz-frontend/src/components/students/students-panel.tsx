import {
    createStudentAccount,
    deleteStudentAccount,
    getStudents,
    updateStudentAccount,
} from "@/api/students"
import { ApiError } from "@/api/client"
import { getAllStudentClasses } from "@/api/classes"
import type { StudentAccount, StudentClass } from "@/api/types"
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
    LoaderCircle,
    Pencil,
    Trash2,
    UserRound,
    UserRoundPlus,
} from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

export function StudentsPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
}: {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
}) {
    const { t } = useTranslation()
    const [students, setStudents] = useState<StudentAccount[]>([])
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [search, setSearch] = useState("")
    const [classFilter, setClassFilter] = useState("")
    const [statusFilter, setStatusFilter] = useState("")
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)
    const [reloadKey, setReloadKey] = useState(0)
    const [isLoading, setIsLoading] = useState(true)
    const [loadError, setLoadError] = useState<string | null>(null)
    const [editing, setEditing] = useState<StudentAccount | null>(null)
    const [deleting, setDeleting] = useState<StudentAccount | null>(null)
    const [displayName, setDisplayName] = useState("")
    const [identifier, setIdentifier] = useState("")
    const [password, setPassword] = useState("")
    const [isActive, setIsActive] = useState(true)
    const [isBusy, setIsBusy] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)

    useEffect(() => {
        let active = true
        getAllStudentClasses()
            .then((items) => active && setClasses(items))
            .catch(() => active && setClasses([]))
        return () => {
            active = false
        }
    }, [reloadKey])

    useEffect(() => {
        let active = true
        getStudents(page, search.trim(), 12, classFilter, statusFilter)
            .then((result) => {
                if (!active) return
                setStudents(result.items)
                setTotalPages(result.totalPages)
                setLoadError(null)
            })
            .catch(() => active && setLoadError(t("students-load-error")))
            .finally(() => active && setIsLoading(false))
        return () => {
            active = false
        }
    }, [classFilter, page, reloadKey, search, statusFilter, t])

    function closeForm() {
        onCreateDialogOpenChange(false)
        setEditing(null)
        setDisplayName("")
        setIdentifier("")
        setPassword("")
        setIsActive(true)
        setFormError(null)
    }

    function edit(student: StudentAccount) {
        setEditing(student)
        setDisplayName(student.display_name)
        setIdentifier(student.identifier)
        setPassword("")
        setIsActive(student.is_active)
        setFormError(null)
    }

    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setIsBusy(true)
        setFormError(null)
        try {
            if (editing) {
                await updateStudentAccount(editing.id, {
                    display_name: displayName.trim(),
                    identifier: identifier.trim(),
                    ...(password ? { password } : {}),
                    is_active: isActive,
                })
            } else {
                await createStudentAccount({
                    display_name: displayName.trim(),
                    identifier: identifier.trim(),
                    password,
                })
            }
            closeForm()
            setReloadKey((value) => value + 1)
        } catch (error) {
            setFormError(
                error instanceof ApiError && error.status === 409
                    ? t("student-account-duplicate")
                    : t("student-account-save-error")
            )
        } finally {
            setIsBusy(false)
        }
    }

    async function confirmDelete() {
        if (!deleting) return
        setIsBusy(true)
        setFormError(null)
        try {
            await deleteStudentAccount(deleting.id)
            setDeleting(null)
            setReloadKey((value) => value + 1)
        } catch {
            setFormError(t("student-account-delete-error"))
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
                            <FieldLabel htmlFor="student-filter-search">
                                {t("search")}
                            </FieldLabel>
                            <Input
                                id="student-filter-search"
                                value={search}
                                onChange={(event) => {
                                    setSearch(event.target.value)
                                    setPage(1)
                                }}
                                placeholder={t("search-student")}
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="student-filter-class">
                                {t("student-class")}
                            </FieldLabel>
                            <select
                                id="student-filter-class"
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={classFilter}
                                onChange={(event) => {
                                    setClassFilter(event.target.value)
                                    setPage(1)
                                }}
                            >
                                <option value="">{t("all-classes")}</option>
                                <option value="unassigned">
                                    {t("student-unassigned")}
                                </option>
                                {classes.map((studentClass) => (
                                    <option
                                        key={studentClass.id}
                                        value={studentClass.id}
                                    >
                                        {studentClass.name}
                                    </option>
                                ))}
                            </select>
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="student-filter-status">
                                {t("account-status")}
                            </FieldLabel>
                            <select
                                id="student-filter-status"
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={statusFilter}
                                onChange={(event) => {
                                    setStatusFilter(event.target.value)
                                    setPage(1)
                                }}
                            >
                                <option value="">{t("all-statuses")}</option>
                                <option value="true">{t("active")}</option>
                                <option value="false">{t("inactive")}</option>
                            </select>
                        </Field>
                        {(search || classFilter || statusFilter) && (
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                    setSearch("")
                                    setClassFilter("")
                                    setStatusFilter("")
                                    setPage(1)
                                }}
                            >
                                {t("clear-filters")}
                            </Button>
                        )}
                    </FieldGroup>
                </aside>
                <div className="min-w-0">
                    {isLoading ? (
                        <div className="flex min-h-40 items-center justify-center">
                            <LoaderCircle className="size-7 animate-spin text-primary" />
                        </div>
                    ) : loadError ? (
                        <p role="alert" className="text-sm text-destructive">
                            {loadError}
                        </p>
                    ) : students.length === 0 ? (
                        <div className="flex min-h-44 flex-col items-center justify-center rounded-xl border border-dashed text-center text-muted-foreground">
                            <UserRound className="mb-2 size-8" />
                            <p className="font-medium">
                                {t("no-student-account")}
                            </p>
                            <p className="mt-1 text-sm">
                                {t("no-student-account-help")}
                            </p>
                        </div>
                    ) : (
                        <div className="grid gap-3 lg:grid-cols-2">
                            {students.map((student) => (
                                <article
                                    key={student.id}
                                    className="flex items-center justify-between gap-3 rounded-xl border p-4"
                                >
                                    <div className="min-w-0">
                                        <p className="truncate font-semibold">
                                            {student.display_name}
                                        </p>
                                        <p className="text-sm text-muted-foreground">
                                            {student.identifier}
                                        </p>
                                        <p className="mt-1 text-xs text-muted-foreground">
                                            {student.class_name ??
                                                t("student-unassigned")}
                                            {!student.is_active &&
                                                ` · ${t("student-disabled")}`}
                                        </p>
                                    </div>
                                    <div className="flex gap-1">
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            aria-label={t("edit-student")}
                                            onClick={() => edit(student)}
                                        >
                                            <Pencil />
                                        </Button>
                                        <Button
                                            size="icon"
                                            variant="ghost"
                                            aria-label={t("delete-student")}
                                            onClick={() => {
                                                setDeleting(student)
                                                setFormError(null)
                                            }}
                                        >
                                            <Trash2 />
                                        </Button>
                                    </div>
                                </article>
                            ))}
                        </div>
                    )}
                    <Pagination
                        currentPage={page}
                        totalPages={totalPages}
                        onPageChange={setPage}
                    />
                </div>
            </div>

            <Dialog
                open={isCreateDialogOpen || editing !== null}
                onOpenChange={(open) => !open && !isBusy && closeForm()}
                title={t(
                    editing ? "edit-student-account" : "create-student-account"
                )}
                description={t("student-account-form-help")}
                className="max-w-lg"
            >
                <form onSubmit={submit}>
                    <FieldGroup>
                        <Field>
                            <FieldLabel htmlFor="account-name">
                                {t("student-name")}
                            </FieldLabel>
                            <Input
                                id="account-name"
                                value={displayName}
                                onChange={(event) =>
                                    setDisplayName(event.target.value)
                                }
                                required
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="account-id">
                                {t("student-id")}
                            </FieldLabel>
                            <Input
                                id="account-id"
                                value={identifier}
                                onChange={(event) =>
                                    setIdentifier(
                                        event.target.value.toLowerCase()
                                    )
                                }
                                pattern="[a-zA-Z0-9._-]+"
                                autoComplete="off"
                                required
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="account-password">
                                {t(
                                    editing
                                        ? "new-password-optional"
                                        : "login-password"
                                )}
                            </FieldLabel>
                            <Input
                                id="account-password"
                                type="password"
                                value={password}
                                onChange={(event) =>
                                    setPassword(event.target.value)
                                }
                                minLength={8}
                                autoComplete="new-password"
                                required={!editing}
                            />
                        </Field>
                        {editing && (
                            <label className="flex items-center gap-2 text-sm">
                                <input
                                    type="checkbox"
                                    checked={isActive}
                                    onChange={(event) =>
                                        setIsActive(event.target.checked)
                                    }
                                />
                                {t("student-account-active")}
                            </label>
                        )}
                        {formError && <FieldError>{formError}</FieldError>}
                        <div className="flex justify-end gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                onClick={closeForm}
                                disabled={isBusy}
                            >
                                {t("cancel")}
                            </Button>
                            <Button type="submit" disabled={isBusy}>
                                {isBusy ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <UserRoundPlus />
                                )}
                                {t("save-student")}
                            </Button>
                        </div>
                    </FieldGroup>
                </form>
            </Dialog>

            <Dialog
                open={deleting !== null}
                onOpenChange={(open) => !open && !isBusy && setDeleting(null)}
                title={t("delete-student")}
                description={t("delete-student-account-help", {
                    name: deleting?.display_name,
                })}
                className="max-w-md"
            >
                {formError && <FieldError>{formError}</FieldError>}
                <div className="mt-4 flex justify-end gap-2">
                    <Button
                        variant="outline"
                        onClick={() => setDeleting(null)}
                        disabled={isBusy}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        variant="destructive"
                        onClick={() => void confirmDelete()}
                        disabled={isBusy}
                    >
                        {isBusy && <LoaderCircle className="animate-spin" />}
                        {t("delete")}
                    </Button>
                </div>
            </Dialog>
        </div>
    )
}

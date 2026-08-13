import {
    createStudentAccount,
    deleteStudentAccount,
    exportStudentCredentials,
    getStudentCredentials,
    getStudents,
    updateStudentAccount,
} from "@/api/students"
import { ApiError } from "@/api/client"
import {
    assignStudentAccount,
    getAllStudentClasses,
    unassignStudentAccount,
} from "@/api/classes"
import type {
    StudentAccount,
    StudentClass,
    StudentCredential,
} from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { Pagination } from "@/components/ui/pagination"
import { formatClassName } from "@/lib/utils"
import {
    LoaderCircle,
    Download,
    KeyRound,
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
    const [firstName, setFirstName] = useState("")
    const [lastName, setLastName] = useState("")
    const [identifier, setIdentifier] = useState("")
    const [password, setPassword] = useState("")
    const [selectedClassId, setSelectedClassId] = useState("")
    const [pendingCreatedAccountId, setPendingCreatedAccountId] = useState<
        number | null
    >(null)
    const [isActive, setIsActive] = useState(true)
    const [isBusy, setIsBusy] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)
    const [credentials, setCredentials] = useState<StudentCredential[] | null>(
        null
    )
    const [credentialsError, setCredentialsError] = useState<string | null>(
        null
    )

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
                if (result.page > result.totalPages) {
                    setPage(result.totalPages)
                }
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
        setFirstName("")
        setLastName("")
        setIdentifier("")
        setPassword("")
        setSelectedClassId("")
        setPendingCreatedAccountId(null)
        setIsActive(true)
        setFormError(null)
    }

    function edit(student: StudentAccount) {
        setEditing(student)
        setDisplayName(student.display_name)
        setIdentifier(student.identifier)
        setPassword("")
        setSelectedClassId(
            student.class_id === null ? "" : String(student.class_id)
        )
        setIsActive(student.is_active)
        setFormError(null)
    }

    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setIsBusy(true)
        setFormError(null)
        let classAssignmentFailed = false
        try {
            if (editing) {
                await updateStudentAccount(editing.id, {
                    display_name: displayName.trim(),
                    identifier: identifier.trim(),
                    ...(password ? { password } : {}),
                    is_active: isActive,
                })
                const nextClassId = selectedClassId
                    ? Number(selectedClassId)
                    : null
                if (nextClassId !== editing.class_id) {
                    try {
                        if (nextClassId !== null) {
                            await assignStudentAccount(nextClassId, editing.id)
                        } else if (editing.class_id !== null) {
                            await unassignStudentAccount(
                                editing.class_id,
                                editing.id
                            )
                        }
                    } catch (error) {
                        classAssignmentFailed = true
                        throw error
                    }
                }
            } else {
                let accountId = pendingCreatedAccountId
                if (accountId === null) {
                    const created = await createStudentAccount({
                        first_name: firstName.trim(),
                        last_name: lastName.trim(),
                    })
                    accountId = created.id
                    setPendingCreatedAccountId(accountId)
                }
                if (selectedClassId) {
                    try {
                        await assignStudentAccount(
                            Number(selectedClassId),
                            accountId
                        )
                    } catch (error) {
                        classAssignmentFailed = true
                        throw error
                    }
                }
            }
            closeForm()
            setReloadKey((value) => value + 1)
        } catch (error) {
            if (classAssignmentFailed && !editing) {
                setReloadKey((value) => value + 1)
            }
            setFormError(
                classAssignmentFailed
                    ? t("student-assignment-error")
                    : error instanceof ApiError && error.status === 409
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

    async function showCredentials() {
        setIsBusy(true)
        setCredentialsError(null)
        try {
            setCredentials(await getStudentCredentials())
        } catch {
            setCredentialsError(t("student-credentials-load-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function exportCredentials() {
        setIsBusy(true)
        setCredentialsError(null)
        try {
            const blob = await exportStudentCredentials()
            const url = URL.createObjectURL(blob)
            const link = document.createElement("a")
            link.href = url
            link.download = "student-credentials.json"
            document.body.append(link)
            link.click()
            link.remove()
            window.setTimeout(() => URL.revokeObjectURL(url), 0)
        } catch {
            setCredentialsError(t("student-credentials-export-error"))
        } finally {
            setIsBusy(false)
        }
    }

    return (
        <div className="mt-6">
            {credentialsError && (
                <p role="alert" className="mb-4 text-sm text-destructive">
                    {credentialsError}
                </p>
            )}
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
                                        {formatClassName(
                                            studentClass.grade_level,
                                            studentClass.name
                                        )}
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
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
                        <h3 className="font-semibold">{t("students")}</h3>
                        <div className="flex flex-wrap gap-2">
                            <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={() => void showCredentials()}
                                disabled={isBusy}
                            >
                                <KeyRound />
                                {t("view-student-credentials")}
                            </Button>
                            <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                onClick={() => void exportCredentials()}
                                disabled={isBusy}
                            >
                                <Download />
                                {t("export-student-credentials")}
                            </Button>
                        </div>
                    </div>
                    {isLoading ? (
                        <div
                            className="flex min-h-40 items-center justify-center"
                            role="status"
                            aria-label={t("page-loading")}
                        >
                            <LoaderCircle className="size-7 animate-spin text-primary motion-reduce:animate-none" />
                        </div>
                    ) : loadError ? (
                        <p role="alert" className="text-sm text-destructive">
                            {loadError}
                        </p>
                    ) : students.length === 0 ? (
                        <div className="flex min-h-44 flex-col items-center justify-center rounded-xl border border-dashed text-center text-muted-foreground">
                            <UserRound className="mb-2 size-8" />
                            <p className="font-medium">
                                {t(
                                    search || classFilter || statusFilter
                                        ? "no-student-matching-filters"
                                        : "no-student-account"
                                )}
                            </p>
                            {!search && !classFilter && !statusFilter && (
                                <p className="mt-1 text-sm">
                                    {t("no-student-account-help")}
                                </p>
                            )}
                        </div>
                    ) : (
                        <div
                            key={students
                                .map((student) => student.id)
                                .join(",")}
                            className="grid animate-in gap-2 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none lg:grid-cols-2"
                        >
                            {students.map((student) => (
                                <article
                                    key={student.id}
                                    className="relative flex items-start gap-2.5 rounded-xl border bg-background p-3"
                                >
                                    <Button
                                        type="button"
                                        size="icon-sm"
                                        variant="ghost"
                                        className="absolute top-4 right-12"
                                        aria-label={t("edit-student")}
                                        title={t("edit-student")}
                                        onClick={() => edit(student)}
                                    >
                                        <Pencil />
                                    </Button>
                                    <Button
                                        type="button"
                                        size="icon-sm"
                                        variant="destructive"
                                        className="absolute top-4 right-4"
                                        aria-label={t("delete-student")}
                                        title={t("delete-student")}
                                        onClick={() => {
                                            setDeleting(student)
                                            setFormError(null)
                                        }}
                                    >
                                        <Trash2 />
                                    </Button>
                                    <div className="rounded-lg bg-primary/10 p-1.5 text-primary">
                                        <UserRound className="size-4" />
                                    </div>
                                    <div className="min-w-0 flex-1 pr-16">
                                        <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                                            {student.identifier}
                                        </p>
                                        <p className="mt-1 font-semibold break-words">
                                            {student.display_name}
                                        </p>
                                        <p className="mt-1 text-xs text-muted-foreground">
                                            {student.class_name
                                                ? formatClassName(
                                                      student.grade_level,
                                                      student.class_name
                                                  )
                                                : t("student-unassigned")}
                                            {!student.is_active &&
                                                ` · ${t("student-disabled")}`}
                                        </p>
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
                description={t(
                    editing
                        ? "student-account-form-help"
                        : "student-id-generated-help"
                )}
                size="md"
            >
                <form onSubmit={submit}>
                    <FieldGroup>
                        <div className="grid items-start gap-4 sm:grid-cols-2">
                            {editing ? (
                                <>
                                    <Field>
                                        <FieldLabel htmlFor="account-name">
                                            {t("student-name")}
                                        </FieldLabel>
                                        <Input
                                            id="account-name"
                                            value={displayName}
                                            onChange={(event) =>
                                                setDisplayName(
                                                    event.target.value
                                                )
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
                                </>
                            ) : (
                                <>
                                    <Field>
                                        <FieldLabel htmlFor="account-first-name">
                                            {t("first-name")}
                                        </FieldLabel>
                                        <Input
                                            id="account-first-name"
                                            value={firstName}
                                            onChange={(event) =>
                                                setFirstName(event.target.value)
                                            }
                                            required
                                        />
                                    </Field>
                                    <Field>
                                        <FieldLabel htmlFor="account-last-name">
                                            {t("last-name")}
                                        </FieldLabel>
                                        <Input
                                            id="account-last-name"
                                            value={lastName}
                                            onChange={(event) =>
                                                setLastName(event.target.value)
                                            }
                                            required
                                        />
                                    </Field>
                                </>
                            )}
                            <Field>
                                <FieldLabel htmlFor="account-class">
                                    {t("student-class")}
                                </FieldLabel>
                                <select
                                    id="account-class"
                                    className={NATIVE_SELECT_CLASS_NAME}
                                    value={selectedClassId}
                                    onChange={(event) =>
                                        setSelectedClassId(event.target.value)
                                    }
                                    disabled={isBusy}
                                >
                                    <option value="">{t("no-class")}</option>
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
                                {editing && (
                                    <p className="text-xs text-muted-foreground">
                                        {t("student-class-help")}
                                    </p>
                                )}
                            </Field>
                            {editing && (
                                <Field>
                                    <FieldLabel htmlFor="account-password">
                                        {t("new-password-optional")}
                                    </FieldLabel>
                                    <PasswordInput
                                        id="account-password"
                                        value={password}
                                        onChange={(event) =>
                                            setPassword(event.target.value)
                                        }
                                        minLength={8}
                                        autoComplete="new-password"
                                    />
                                </Field>
                            )}
                        </div>
                        {editing && (
                            <label className="flex items-center gap-2 text-sm">
                                <input
                                    type="checkbox"
                                    className="accent-primary"
                                    checked={isActive}
                                    onChange={(event) =>
                                        setIsActive(event.target.checked)
                                    }
                                />
                                {t("student-account-active")}
                            </label>
                        )}
                        {formError && <FieldError>{formError}</FieldError>}
                        <div className="flex justify-end gap-2 border-t pt-4">
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
                                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                ) : editing ? (
                                    <Pencil />
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
                open={credentials !== null}
                onOpenChange={(open) => !open && setCredentials(null)}
                title={t("student-credentials")}
                description={t("student-credentials-sensitive-help")}
                size="xl"
            >
                {credentials && (
                    <div className="space-y-4">
                        <div className="max-h-[55vh] overflow-auto rounded-lg border">
                            <table className="w-full text-left text-sm">
                                <thead className="sticky top-0 bg-muted">
                                    <tr>
                                        <th className="px-3 py-2">
                                            {t("student-name")}
                                        </th>
                                        <th className="px-3 py-2">
                                            {t("student-id")}
                                        </th>
                                        <th className="px-3 py-2">
                                            {t("login-password")}
                                        </th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {credentials.map((credential) => (
                                        <tr
                                            key={credential.identifier}
                                            className="border-t"
                                        >
                                            <td className="px-3 py-2">
                                                {credential.display_name}
                                            </td>
                                            <td className="px-3 py-2 font-mono">
                                                {credential.identifier}
                                            </td>
                                            <td className="px-3 py-2 font-mono">
                                                {credential.password ??
                                                    t("password-unavailable")}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                        <div className="flex justify-end">
                            <Button
                                type="button"
                                onClick={() => setCredentials(null)}
                            >
                                {t("close")}
                            </Button>
                        </div>
                    </div>
                )}
            </Dialog>

            <Dialog
                open={deleting !== null}
                onOpenChange={(open) => !open && !isBusy && setDeleting(null)}
                title={t("delete-student")}
                description={t("delete-student-account-help", {
                    name: deleting?.display_name,
                })}
                size="sm"
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

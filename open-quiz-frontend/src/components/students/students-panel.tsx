import {
    deleteStudentAccount,
    exportStudentCredentials,
    getStudents,
} from "@/api/students"
import { getAllStudentClasses } from "@/api/classes"
import type { StudentAccount, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { StudentFormDialog } from "@/components/students/student-form-dialog"
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { Pagination } from "@/components/ui/pagination"
import { formatClassName, saveBlob } from "@/lib/utils"
import { LoaderCircle, Download, Pencil, Trash2, UserRound } from "lucide-react"
import { usePagedList } from "@/hooks/use-paged-list"
import { useResource } from "@/hooks/use-resource"
import { useState } from "react"
import { useTranslation } from "react-i18next"
import { apiErrorMessage } from "@/lib/errors"

const STUDENTS_PAGE_SIZE = 12

function loadStudents(
    page: number,
    filters: { search: string; classId: string; status: string },
    _focus: unknown,
    signal: AbortSignal
) {
    return getStudents(
        page,
        filters.search.trim(),
        STUDENTS_PAGE_SIZE,
        filters.classId,
        filters.status,
        signal
    )
}

export function StudentsPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
}: {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
}) {
    const { t } = useTranslation()
    const studentList = usePagedList(loadStudents, {
        search: "",
        classId: "",
        status: "",
    })
    const students = studentList.items
    const {
        search,
        classId: classFilter,
        status: statusFilter,
    } = studentList.filters
    const isLoading = !studentList.hasSettled
    const loadError = studentList.error ? t("students-load-error") : null
    const classList = useResource(getAllStudentClasses)
    const classes: StudentClass[] = classList.error
        ? []
        : (classList.data ?? [])
    const [editing, setEditing] = useState<StudentAccount | null>(null)
    const [deleting, setDeleting] = useState<StudentAccount | null>(null)
    const [isBusy, setIsBusy] = useState(false)
    const [formError, setFormError] = useState<string | null>(null)
    const [exportError, setExportError] = useState<string | null>(null)

    function reloadLists() {
        studentList.reload()
        classList.reload()
    }

    function closeForm() {
        onCreateDialogOpenChange(false)
        setEditing(null)
    }

    function edit(student: StudentAccount) {
        setFormError(null)
        setEditing(student)
    }

    async function confirmDelete() {
        if (!deleting) return
        setIsBusy(true)
        setFormError(null)
        try {
            await deleteStudentAccount(deleting.id)
            setDeleting(null)
            reloadLists()
        } catch (caught) {
            setFormError(
                apiErrorMessage(caught, t, t("student-account-delete-error"))
            )
        } finally {
            setIsBusy(false)
        }
    }

    async function exportCredentials() {
        setIsBusy(true)
        setExportError(null)
        try {
            saveBlob(
                await exportStudentCredentials(),
                "student-credentials.json"
            )
        } catch {
            setExportError(t("student-credentials-export-error"))
        } finally {
            setIsBusy(false)
        }
    }

    return (
        <div className="mt-6">
            {exportError && (
                <p role="alert" className="mb-4 text-sm text-destructive">
                    {exportError}
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
                                    studentList.setFilter(
                                        "search",
                                        event.target.value
                                    )
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
                                    studentList.setFilter(
                                        "classId",
                                        event.target.value
                                    )
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
                                    studentList.setFilter(
                                        "status",
                                        event.target.value
                                    )
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
                                    studentList.resetFilters()
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
                                        className="absolute end-12 top-4"
                                        aria-label={t("edit-student-named", {
                                            name: student.display_name,
                                        })}
                                        title={t("edit-student")}
                                        onClick={() => edit(student)}
                                    >
                                        <Pencil />
                                    </Button>
                                    <Button
                                        type="button"
                                        size="icon-sm"
                                        variant="destructive"
                                        className="absolute end-4 top-4"
                                        aria-label={t("delete-student-named", {
                                            name: student.display_name,
                                        })}
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
                                    <div className="min-w-0 flex-1 pe-20">
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
                        currentPage={studentList.page}
                        totalPages={studentList.totalPages}
                        onPageChange={studentList.showPage}
                    />
                </div>
            </div>

            {(isCreateDialogOpen || editing !== null) && (
                <StudentFormDialog
                    key={editing?.id ?? "new"}
                    student={editing}
                    classes={classes}
                    onClose={closeForm}
                    onListsChanged={reloadLists}
                />
            )}

            <ConfirmDeleteDialog
                open={deleting !== null}
                title={t("delete-student")}
                description={t("delete-student-account-help", {
                    name: deleting?.display_name,
                })}
                isBusy={isBusy}
                error={formError}
                onClose={() => setDeleting(null)}
                onConfirm={() => void confirmDelete()}
            />
        </div>
    )
}

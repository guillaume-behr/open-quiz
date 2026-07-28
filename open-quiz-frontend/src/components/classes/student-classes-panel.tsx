import {
    createStudent,
    createStudentClass,
    deleteStudent,
    deleteStudentClass,
    getStudentClasses,
    updateStudent,
    updateStudentClass,
} from "@/api/classes"
import { ApiError } from "@/api/client"
import { getQuestionBanks } from "@/api/question-banks"
import type { Student, StudentClass } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
    LoaderCircle,
    Eye,
    Pencil,
    Plus,
    Trash2,
    UserPlus,
    UsersRound,
} from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

type StudentClassesPanelProps = {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
}

const selectClassName =
    "h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

export function StudentClassesPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
}: StudentClassesPanelProps) {
    const { t } = useTranslation()
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [loadError, setLoadError] = useState<string | null>(null)
    const [className, setClassName] = useState("")
    const [gradeLevel, setGradeLevel] = useState("")
    const [isCreatingClass, setIsCreatingClass] = useState(false)
    const [classError, setClassError] = useState<string | null>(null)
    const [editingClass, setEditingClass] = useState<StudentClass | null>(null)
    const [classForStudent, setClassForStudent] = useState<StudentClass | null>(
        null
    )
    const [studentFirstName, setStudentFirstName] = useState("")
    const [studentLastName, setStudentLastName] = useState("")
    const [gradeLevels, setGradeLevels] = useState<string[]>([])
    const [isCreatingStudent, setIsCreatingStudent] = useState(false)
    const [studentError, setStudentError] = useState<string | null>(null)
    const [editingStudent, setEditingStudent] = useState<Student | null>(null)
    const [classToDelete, setClassToDelete] = useState<StudentClass | null>(
        null
    )
    const [studentToDelete, setStudentToDelete] = useState<Student | null>(null)
    const [isDeleting, setIsDeleting] = useState(false)
    const [deleteError, setDeleteError] = useState<string | null>(null)
    const [managedClassId, setManagedClassId] = useState<number | null>(null)
    const [classFilter, setClassFilter] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
    const managedClass =
        classes.find((studentClass) => studentClass.id === managedClassId) ??
        null
    const filteredClasses = classes.filter(
        (studentClass) =>
            (!classFilter ||
                studentClass.name
                    .toLocaleLowerCase("fr")
                    .includes(classFilter.toLocaleLowerCase("fr"))) &&
            (!gradeLevelFilter || studentClass.grade_level === gradeLevelFilter)
    )

    useEffect(() => {
        let isActive = true
        Promise.all([getStudentClasses(), getQuestionBanks()])
            .then(([loadedClasses, banks]) => {
                if (!isActive) return
                setClasses(loadedClasses)
                setGradeLevels(
                    Array.from(
                        new Set([
                            ...banks.map((bank) => bank.grade_level),
                            ...loadedClasses.map(
                                (studentClass) => studentClass.grade_level
                            ),
                        ])
                    ).sort((first, second) => first.localeCompare(second, "fr"))
                )
            })
            .catch(() => {
                if (isActive) setLoadError(t("classes-load-error"))
            })
            .finally(() => {
                if (isActive) setIsLoading(false)
            })
        return () => {
            isActive = false
        }
    }, [t])

    async function handleCreateClass(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setClassError(null)
        setIsCreatingClass(true)
        try {
            const savedClass = editingClass
                ? await updateStudentClass(
                      editingClass.id,
                      className.trim(),
                      gradeLevel.trim()
                  )
                : await createStudentClass(className.trim(), gradeLevel.trim())
            setClasses((current) =>
                (editingClass
                    ? current.map((studentClass) =>
                          studentClass.id === savedClass.id
                              ? savedClass
                              : studentClass
                      )
                    : [...current, savedClass]
                ).sort((first, second) =>
                    `${first.grade_level}-${first.name}`.localeCompare(
                        `${second.grade_level}-${second.name}`,
                        "fr"
                    )
                )
            )
            setClassName("")
            setGradeLevel("")
            setEditingClass(null)
            onCreateDialogOpenChange(false)
        } catch (error) {
            setClassError(
                error instanceof ApiError && error.status === 409
                    ? t("class-duplicate-error")
                    : t("class-create-error")
            )
        } finally {
            setIsCreatingClass(false)
        }
    }

    async function handleCreateStudent(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!classForStudent) return
        setStudentError(null)
        setIsCreatingStudent(true)
        try {
            const displayName =
                `${studentFirstName.trim()} ${studentLastName.trim()}`.trim()
            const student = editingStudent
                ? await updateStudent(editingStudent.id, displayName)
                : await createStudent(classForStudent.id, displayName)
            setClasses((current) =>
                current.map((studentClass) =>
                    studentClass.id === classForStudent.id
                        ? {
                              ...studentClass,
                              students: (editingStudent
                                  ? studentClass.students.map((item) =>
                                        item.id === student.id ? student : item
                                    )
                                  : [...studentClass.students, student]
                              ).sort((first, second) =>
                                  first.display_name.localeCompare(
                                      second.display_name,
                                      "fr"
                                  )
                              ),
                              student_count: editingStudent
                                  ? studentClass.student_count
                                  : studentClass.student_count + 1,
                          }
                        : studentClass
                )
            )
            setStudentFirstName("")
            setStudentLastName("")
            setEditingStudent(null)
            setClassForStudent(null)
        } catch (error) {
            setStudentError(
                error instanceof ApiError && error.status === 409
                    ? t("student-duplicate-error")
                    : t("student-create-error")
            )
        } finally {
            setIsCreatingStudent(false)
        }
    }

    async function handleDelete(): Promise<void> {
        setDeleteError(null)
        setIsDeleting(true)
        try {
            if (classToDelete) {
                await deleteStudentClass(classToDelete.id)
                setClasses((current) =>
                    current.filter(
                        (studentClass) => studentClass.id !== classToDelete.id
                    )
                )
                setClassToDelete(null)
            } else if (studentToDelete) {
                await deleteStudent(studentToDelete.id)
                setClasses((current) =>
                    current.map((studentClass) =>
                        studentClass.id === studentToDelete.class_id
                            ? {
                                  ...studentClass,
                                  students: studentClass.students.filter(
                                      (student) =>
                                          student.id !== studentToDelete.id
                                  ),
                                  student_count: Math.max(
                                      0,
                                      studentClass.student_count - 1
                                  ),
                              }
                            : studentClass
                    )
                )
                setStudentToDelete(null)
            }
        } catch {
            setDeleteError(t("class-student-delete-error"))
        } finally {
            setIsDeleting(false)
        }
    }

    return (
        <div className="mt-6">
            {isLoading ? (
                <div className="flex min-h-40 items-center justify-center">
                    <LoaderCircle className="size-7 animate-spin text-primary" />
                </div>
            ) : loadError ? (
                <p
                    role="alert"
                    className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
                >
                    {loadError}
                </p>
            ) : classes.length === 0 ? (
                <div className="grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
                    <aside className="h-fit rounded-xl border bg-background p-4">
                        <h3 className="font-semibold">{t("filters")}</h3>
                        <FieldGroup className="mt-4 gap-4">
                            <Field>
                                <FieldLabel htmlFor="empty-class-filter">
                                    {t("search")}
                                </FieldLabel>
                                <Input
                                    id="empty-class-filter"
                                    value={classFilter}
                                    onChange={(event) =>
                                        setClassFilter(event.target.value)
                                    }
                                    placeholder={t("search-class")}
                                />
                            </Field>
                            <Field>
                                <FieldLabel htmlFor="empty-class-grade-filter">
                                    {t("grade-level")}
                                </FieldLabel>
                                <select
                                    id="empty-class-grade-filter"
                                    className={selectClassName}
                                    value={gradeLevelFilter}
                                    onChange={(event) =>
                                        setGradeLevelFilter(event.target.value)
                                    }
                                >
                                    <option value="">
                                        {t("all-grade-levels")}
                                    </option>
                                    {gradeLevels.map((level) => (
                                        <option key={level} value={level}>
                                            {level}
                                        </option>
                                    ))}
                                </select>
                            </Field>
                        </FieldGroup>
                    </aside>
                    <div className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                        <UsersRound className="mb-2 size-8" />
                        <p className="font-medium">{t("no-class")}</p>
                        <p className="mt-1 text-sm">{t("no-class-help")}</p>
                    </div>
                </div>
            ) : (
                <div className="grid items-start gap-5 xl:grid-cols-[minmax(220px,280px)_minmax(0,1fr)]">
                    <aside className="h-fit rounded-xl border bg-background p-4">
                        <h3 className="font-semibold">{t("filters")}</h3>
                        <FieldGroup className="mt-4 gap-4">
                            <Field>
                                <FieldLabel htmlFor="class-filter">
                                    {t("search")}
                                </FieldLabel>
                                <Input
                                    id="class-filter"
                                    value={classFilter}
                                    onChange={(event) =>
                                        setClassFilter(event.target.value)
                                    }
                                    placeholder={t("search-class")}
                                />
                            </Field>
                            <Field>
                                <FieldLabel htmlFor="class-grade-filter">
                                    {t("grade-level")}
                                </FieldLabel>
                                <select
                                    id="class-grade-filter"
                                    className={selectClassName}
                                    value={gradeLevelFilter}
                                    onChange={(event) =>
                                        setGradeLevelFilter(event.target.value)
                                    }
                                >
                                    <option value="">
                                        {t("all-grade-levels")}
                                    </option>
                                    {gradeLevels.map((level) => (
                                        <option key={level} value={level}>
                                            {level}
                                        </option>
                                    ))}
                                </select>
                            </Field>
                            {(classFilter || gradeLevelFilter) && (
                                <Button
                                    type="button"
                                    variant="outline"
                                    onClick={() => {
                                        setClassFilter("")
                                        setGradeLevelFilter("")
                                    }}
                                >
                                    {t("clear-filters")}
                                </Button>
                            )}
                        </FieldGroup>
                    </aside>
                    {filteredClasses.length === 0 ? (
                        <p className="rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                            {t("no-class-filtered")}
                        </p>
                    ) : (
                        <div className="grid gap-4 lg:grid-cols-2">
                            {filteredClasses.map((studentClass) => (
                                <article
                                    key={studentClass.id}
                                    className="flex h-full flex-col rounded-xl border bg-background p-4"
                                >
                                    <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                                        {studentClass.grade_level}
                                    </p>
                                    <h3 className="mt-1 text-lg font-semibold">
                                        {studentClass.name}
                                    </h3>
                                    <div className="mt-4 grid grid-cols-2 gap-3">
                                        <div className="rounded-lg bg-primary/5 p-3">
                                            <p className="text-2xl font-bold text-primary">
                                                {studentClass.student_count}
                                            </p>
                                            <p className="text-sm text-muted-foreground">
                                                {t("students")}
                                            </p>
                                        </div>
                                        <div className="rounded-lg bg-primary/5 p-3">
                                            <p className="text-2xl font-bold text-primary">
                                                {
                                                    studentClass.completed_quiz_count
                                                }
                                            </p>
                                            <p className="text-sm text-muted-foreground">
                                                {t("completed-quizzes")}
                                            </p>
                                        </div>
                                    </div>
                                    <Button
                                        type="button"
                                        className="mt-4 w-full"
                                        variant="outline"
                                        onClick={() =>
                                            setManagedClassId(studentClass.id)
                                        }
                                    >
                                        <Eye />
                                        {t("view-class")}
                                    </Button>
                                </article>
                            ))}
                        </div>
                    )}
                </div>
            )}

            <Dialog
                open={managedClass !== null}
                onOpenChange={(open) => {
                    if (!open) setManagedClassId(null)
                }}
                title={managedClass?.name ?? ""}
                description={
                    managedClass
                        ? `${managedClass.grade_level} — ${t("student-count", {
                              count: managedClass.student_count,
                          })}`
                        : undefined
                }
                className="max-w-2xl"
            >
                {managedClass && (
                    <div>
                        <div className="grid gap-2 sm:flex sm:flex-wrap sm:justify-end">
                            <Button
                                type="button"
                                variant="outline"
                                onClick={() => {
                                    setEditingClass(managedClass)
                                    setClassName(managedClass.name)
                                    setGradeLevel(managedClass.grade_level)
                                    setClassError(null)
                                    setManagedClassId(null)
                                }}
                            >
                                <Pencil />
                                {t("edit-class")}
                            </Button>
                            <Button
                                type="button"
                                onClick={() => {
                                    setStudentError(null)
                                    setClassForStudent(managedClass)
                                }}
                            >
                                <UserPlus />
                                {t("add-student")}
                            </Button>
                            <Button
                                type="button"
                                variant="destructive"
                                onClick={() => setClassToDelete(managedClass)}
                            >
                                <Trash2 />
                                {t("delete-class")}
                            </Button>
                        </div>
                        {managedClass.students.length === 0 ? (
                            <p className="mt-5 rounded-lg border border-dashed p-5 text-center text-sm text-muted-foreground">
                                {t("no-student")}
                            </p>
                        ) : (
                            <ul className="mt-5 divide-y rounded-lg border">
                                {managedClass.students.map((student) => (
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
                                                onClick={() => {
                                                    setClassForStudent(
                                                        managedClass
                                                    )
                                                    setEditingStudent(student)
                                                    const [
                                                        firstName,
                                                        ...lastName
                                                    ] =
                                                        student.display_name.split(
                                                            " "
                                                        )
                                                    setStudentFirstName(
                                                        firstName
                                                    )
                                                    setStudentLastName(
                                                        lastName.join(" ")
                                                    )
                                                    setStudentError(null)
                                                }}
                                            >
                                                <Pencil />
                                            </Button>
                                            <Button
                                                type="button"
                                                size="icon"
                                                variant="ghost"
                                                aria-label={t("delete-student")}
                                                onClick={() =>
                                                    setStudentToDelete(student)
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

            <Dialog
                open={isCreateDialogOpen || editingClass !== null}
                onOpenChange={(open) => {
                    if (isCreatingClass) return
                    if (!open) {
                        onCreateDialogOpenChange(false)
                        setEditingClass(null)
                        setClassName("")
                        setGradeLevel("")
                        setClassError(null)
                    }
                }}
                title={t(editingClass ? "edit-class" : "create-class")}
                description={t("create-class-help")}
                className="max-w-lg"
            >
                <form onSubmit={handleCreateClass}>
                    <FieldGroup>
                        <Field>
                            <FieldLabel htmlFor="class-name">
                                {t("class-name")}
                            </FieldLabel>
                            <Input
                                id="class-name"
                                list="existing-class-names"
                                value={className}
                                onChange={(event) =>
                                    setClassName(event.target.value)
                                }
                                placeholder={t("class-name-placeholder")}
                                maxLength={120}
                                required
                            />
                            <datalist id="existing-class-names">
                                {classes.map((studentClass) => (
                                    <option
                                        key={studentClass.id}
                                        value={studentClass.name}
                                    />
                                ))}
                            </datalist>
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="class-grade">
                                {t("grade-level")}
                            </FieldLabel>
                            <select
                                id="class-grade"
                                className={selectClassName}
                                value={gradeLevel}
                                onChange={(event) =>
                                    setGradeLevel(event.target.value)
                                }
                                required
                            >
                                <option value="" disabled>
                                    {t("choose-grade-level")}
                                </option>
                                {gradeLevels.map((level) => (
                                    <option key={level} value={level}>
                                        {level}
                                    </option>
                                ))}
                            </select>
                        </Field>
                        {classError && <FieldError>{classError}</FieldError>}
                        <div className="flex justify-end gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                disabled={isCreatingClass}
                                onClick={() => {
                                    setEditingClass(null)
                                    setClassName("")
                                    setGradeLevel("")
                                    setClassError(null)
                                    onCreateDialogOpenChange(false)
                                }}
                            >
                                {t("cancel")}
                            </Button>
                            <Button type="submit" disabled={isCreatingClass}>
                                {isCreatingClass ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <Plus />
                                )}
                                {t(
                                    editingClass ? "save-class" : "create-class"
                                )}
                            </Button>
                        </div>
                    </FieldGroup>
                </form>
            </Dialog>

            <Dialog
                open={classForStudent !== null}
                onOpenChange={(open) => {
                    if (!open && !isCreatingStudent) {
                        setClassForStudent(null)
                        setEditingStudent(null)
                        setStudentFirstName("")
                        setStudentLastName("")
                    }
                }}
                title={t(editingStudent ? "edit-student" : "add-student")}
                description={classForStudent?.name}
                className="max-w-lg"
            >
                <form onSubmit={handleCreateStudent}>
                    <FieldGroup>
                        <Field>
                            <FieldLabel htmlFor="student-first-name">
                                {t("first-name")}
                            </FieldLabel>
                            <Input
                                id="student-first-name"
                                value={studentFirstName}
                                onChange={(event) =>
                                    setStudentFirstName(event.target.value)
                                }
                                maxLength={120}
                                required
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="student-last-name">
                                {t("last-name")}
                            </FieldLabel>
                            <Input
                                id="student-last-name"
                                value={studentLastName}
                                onChange={(event) =>
                                    setStudentLastName(event.target.value)
                                }
                                maxLength={120}
                                required
                            />
                            <p className="text-xs text-muted-foreground">
                                {t("student-id-generated-help")}
                            </p>
                        </Field>
                        {studentError && (
                            <FieldError>{studentError}</FieldError>
                        )}
                        <div className="flex justify-end gap-2">
                            <Button
                                type="button"
                                variant="outline"
                                disabled={isCreatingStudent}
                                onClick={() => {
                                    setClassForStudent(null)
                                    setEditingStudent(null)
                                    setStudentFirstName("")
                                    setStudentLastName("")
                                    setStudentError(null)
                                }}
                            >
                                {t("cancel")}
                            </Button>
                            <Button type="submit" disabled={isCreatingStudent}>
                                {isCreatingStudent ? (
                                    <LoaderCircle className="animate-spin" />
                                ) : (
                                    <UserPlus />
                                )}
                                {t(
                                    editingStudent
                                        ? "save-student"
                                        : "add-student"
                                )}
                            </Button>
                        </div>
                    </FieldGroup>
                </form>
            </Dialog>

            <Dialog
                open={classToDelete !== null || studentToDelete !== null}
                onOpenChange={(open) => {
                    if (!open && !isDeleting) {
                        setClassToDelete(null)
                        setStudentToDelete(null)
                        setDeleteError(null)
                    }
                }}
                title={t(classToDelete ? "delete-class" : "delete-student")}
                description={t(
                    classToDelete ? "delete-class-help" : "delete-student-help",
                    {
                        name:
                            classToDelete?.name ??
                            studentToDelete?.display_name ??
                            "",
                    }
                )}
                className="max-w-md"
            >
                {deleteError && <FieldError>{deleteError}</FieldError>}
                <div className="mt-4 flex justify-end gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        disabled={isDeleting}
                        onClick={() => {
                            setClassToDelete(null)
                            setStudentToDelete(null)
                        }}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        type="button"
                        variant="destructive"
                        disabled={isDeleting}
                        onClick={() => void handleDelete()}
                    >
                        {isDeleting && (
                            <LoaderCircle className="animate-spin" />
                        )}
                        {t("delete")}
                    </Button>
                </div>
            </Dialog>
        </div>
    )
}

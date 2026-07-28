import {
    ApiError,
    createStudent,
    createStudentClass,
    deleteStudent,
    deleteStudentClass,
    getStudentClasses,
    updateStudent,
    updateStudentClass,
    type Student,
    type StudentClass,
} from "@/api/api"
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
    const [classForStudent, setClassForStudent] =
        useState<StudentClass | null>(null)
    const [studentIdentifier, setStudentIdentifier] = useState("")
    const [studentName, setStudentName] = useState("")
    const [isCreatingStudent, setIsCreatingStudent] = useState(false)
    const [studentError, setStudentError] = useState<string | null>(null)
    const [editingStudent, setEditingStudent] = useState<Student | null>(null)
    const [classToDelete, setClassToDelete] = useState<StudentClass | null>(
        null
    )
    const [studentToDelete, setStudentToDelete] = useState<Student | null>(
        null
    )
    const [isDeleting, setIsDeleting] = useState(false)
    const [deleteError, setDeleteError] = useState<string | null>(null)

    useEffect(() => {
        let isActive = true
        getStudentClasses()
            .then((loaded) => {
                if (isActive) setClasses(loaded)
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
                : await createStudentClass(
                      className.trim(),
                      gradeLevel.trim()
                  )
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
            const student = editingStudent
                ? await updateStudent(
                      editingStudent.id,
                      studentIdentifier.trim(),
                      studentName.trim()
                  )
                : await createStudent(
                      classForStudent.id,
                      studentIdentifier.trim(),
                      studentName.trim()
                  )
            setClasses((current) =>
                current.map((studentClass) =>
                    studentClass.id === classForStudent.id
                        ? {
                              ...studentClass,
                              students: (
                                  editingStudent
                                      ? studentClass.students.map((item) =>
                                            item.id === student.id
                                                ? student
                                                : item
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
            setStudentIdentifier("")
            setStudentName("")
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
                        (studentClass) =>
                            studentClass.id !== classToDelete.id
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
                <div className="flex min-h-40 flex-col items-center justify-center rounded-xl border border-dashed p-6 text-center text-muted-foreground">
                    <UsersRound className="mb-2 size-8" />
                    <p className="font-medium">{t("no-class")}</p>
                    <p className="mt-1 text-sm">{t("no-class-help")}</p>
                </div>
            ) : (
                <div className="grid gap-4 xl:grid-cols-2">
                    {classes.map((studentClass) => (
                        <article
                            key={studentClass.id}
                            className="rounded-xl border bg-background p-4"
                        >
                            <div className="flex items-start justify-between gap-3">
                                <div>
                                    <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                                        {studentClass.grade_level}
                                    </p>
                                    <h3 className="mt-1 font-semibold">
                                        {studentClass.name}
                                    </h3>
                                    <p className="mt-1 text-sm text-muted-foreground">
                                        {t("student-count", {
                                            count: studentClass.student_count,
                                        })}
                                    </p>
                                </div>
                                <div className="flex gap-2">
                                    <Button
                                        type="button"
                                        size="icon"
                                        variant="outline"
                                        aria-label={t("edit-class")}
                                        onClick={() => {
                                            setEditingClass(studentClass)
                                            setClassName(studentClass.name)
                                            setGradeLevel(
                                                studentClass.grade_level
                                            )
                                            setClassError(null)
                                        }}
                                    >
                                        <Pencil />
                                    </Button>
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant="outline"
                                        onClick={() => {
                                            setStudentError(null)
                                            setClassForStudent(studentClass)
                                        }}
                                    >
                                        <UserPlus />
                                        {t("add-student")}
                                    </Button>
                                    <Button
                                        type="button"
                                        size="icon"
                                        variant="destructive"
                                        aria-label={t("delete-class")}
                                        onClick={() =>
                                            setClassToDelete(studentClass)
                                        }
                                    >
                                        <Trash2 />
                                    </Button>
                                </div>
                            </div>
                            {studentClass.students.length === 0 ? (
                                <p className="mt-4 rounded-lg border border-dashed p-4 text-center text-sm text-muted-foreground">
                                    {t("no-student")}
                                </p>
                            ) : (
                                <ul className="mt-4 divide-y rounded-lg border">
                                    {studentClass.students.map((student) => (
                                        <li
                                            key={student.id}
                                            className="flex items-center justify-between gap-3 px-3 py-2"
                                        >
                                            <div className="min-w-0">
                                                <p className="font-medium">
                                                    {student.display_name}
                                                </p>
                                                <p className="text-xs text-muted-foreground">
                                                    {student.identifier}
                                                </p>
                                            </div>
                                            <Button
                                                type="button"
                                                size="icon"
                                                variant="ghost"
                                                aria-label={t("edit-student")}
                                                onClick={() => {
                                                    setClassForStudent(
                                                        studentClass
                                                    )
                                                    setEditingStudent(student)
                                                    setStudentName(
                                                        student.display_name
                                                    )
                                                    setStudentIdentifier(
                                                        student.identifier
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
                                                aria-label={t(
                                                    "delete-student"
                                                )}
                                                onClick={() =>
                                                    setStudentToDelete(student)
                                                }
                                            >
                                                <Trash2 />
                                            </Button>
                                        </li>
                                    ))}
                                </ul>
                            )}
                        </article>
                    ))}
                </div>
            )}

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
                                value={className}
                                onChange={(event) =>
                                    setClassName(event.target.value)
                                }
                                placeholder={t("class-name-placeholder")}
                                maxLength={120}
                                required
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="class-grade">
                                {t("grade-level")}
                            </FieldLabel>
                            <Input
                                id="class-grade"
                                value={gradeLevel}
                                onChange={(event) =>
                                    setGradeLevel(event.target.value)
                                }
                                placeholder={t("grade-level-placeholder")}
                                maxLength={80}
                                required
                            />
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
                                    editingClass
                                        ? "save-class"
                                        : "create-class"
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
                        setStudentName("")
                        setStudentIdentifier("")
                    }
                }}
                title={t(
                    editingStudent ? "edit-student" : "add-student"
                )}
                description={classForStudent?.name}
                className="max-w-lg"
            >
                <form onSubmit={handleCreateStudent}>
                    <FieldGroup>
                        <Field>
                            <FieldLabel htmlFor="student-name">
                                {t("student-name")}
                            </FieldLabel>
                            <Input
                                id="student-name"
                                value={studentName}
                                onChange={(event) =>
                                    setStudentName(event.target.value)
                                }
                                maxLength={120}
                                required
                            />
                        </Field>
                        <Field>
                            <FieldLabel htmlFor="student-identifier">
                                {t("student-id")}
                            </FieldLabel>
                            <Input
                                id="student-identifier"
                                value={studentIdentifier}
                                onChange={(event) =>
                                    setStudentIdentifier(event.target.value)
                                }
                                maxLength={80}
                                spellCheck={false}
                                required
                            />
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
                                    setStudentName("")
                                    setStudentIdentifier("")
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
                title={t(
                    classToDelete ? "delete-class" : "delete-student"
                )}
                description={t(
                    classToDelete
                        ? "delete-class-help"
                        : "delete-student-help",
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

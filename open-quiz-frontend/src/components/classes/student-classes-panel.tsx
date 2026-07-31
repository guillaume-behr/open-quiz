import {
    createStudent,
    createStudentClass,
    deleteStudent,
    deleteStudentClass,
    downloadStudents,
    getStudentClasses,
    importStudents,
    updateStudent,
    updateStudentClass,
} from "@/api/classes"
import { ApiError } from "@/api/client"
import type { GradeLevel, Student, StudentClass } from "@/api/types"
import { ClassFormDialog } from "@/components/classes/class-form-dialog"
import { ManagedClassDialog } from "@/components/classes/managed-class-dialog"
import {
    DeleteClassMemberDialog,
    ImportStudentsDialog,
} from "@/components/classes/student-class-secondary-dialogs"
import { StudentFormDialog } from "@/components/classes/student-form-dialog"
import { StudentClassesList } from "@/components/classes/student-classes-list"
import { type FormEvent, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

type StudentClassesPanelProps = {
    isCreateDialogOpen: boolean
    onCreateDialogOpenChange: (open: boolean) => void
    gradeLevels: GradeLevel[]
    onCreateGradeLevel: (name: string) => Promise<GradeLevel>
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
}

function saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
}

function studentsFilename(studentClass: StudentClass): string {
    const safeName = studentClass.name
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .replace(/[^a-zA-Z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .toLowerCase()
    return `classe-${safeName || studentClass.id}-eleves.json`
}

export function StudentClassesPanel({
    isCreateDialogOpen,
    onCreateDialogOpenChange,
    gradeLevels,
    onCreateGradeLevel,
    onDeleteGradeLevel,
}: StudentClassesPanelProps) {
    const { t } = useTranslation()
    const [classes, setClasses] = useState<StudentClass[]>([])
    const [page, setPage] = useState(1)
    const [totalPages, setTotalPages] = useState(1)
    const [reloadKey, setReloadKey] = useState(0)
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
    const [isAddingGradeLevel, setIsAddingGradeLevel] = useState(false)
    const [newGradeLevel, setNewGradeLevel] = useState("")
    const [isCreatingStudent, setIsCreatingStudent] = useState(false)
    const [studentError, setStudentError] = useState<string | null>(null)
    const [editingStudent, setEditingStudent] = useState<Student | null>(null)
    const [classToDelete, setClassToDelete] = useState<StudentClass | null>(
        null
    )
    const [studentToDelete, setStudentToDelete] = useState<Student | null>(null)
    const [classForImport, setClassForImport] = useState<StudentClass | null>(
        null
    )
    const [importFile, setImportFile] = useState<File | null>(null)
    const [isStudentBatchBusy, setIsStudentBatchBusy] = useState(false)
    const [studentBatchError, setStudentBatchError] = useState<string | null>(
        null
    )
    const [isDeleting, setIsDeleting] = useState(false)
    const [deleteError, setDeleteError] = useState<string | null>(null)
    const [managedClassId, setManagedClassId] = useState<number | null>(null)
    const [classFilter, setClassFilter] = useState("")
    const [gradeLevelFilter, setGradeLevelFilter] = useState("")
    const importInputRef = useRef<HTMLInputElement>(null)
    const managedClass =
        classes.find((studentClass) => studentClass.id === managedClassId) ??
        null
    const filteredClasses = classes

    async function handleExportStudents(
        studentClass: StudentClass
    ): Promise<void> {
        setStudentBatchError(null)
        setIsStudentBatchBusy(true)
        try {
            saveBlob(
                await downloadStudents(studentClass.id),
                studentsFilename(studentClass)
            )
        } catch {
            setStudentBatchError(t("students-export-error"))
        } finally {
            setIsStudentBatchBusy(false)
        }
    }

    async function handleImportStudents(
        event: FormEvent<HTMLFormElement>
    ): Promise<void> {
        event.preventDefault()
        if (!classForImport || !importFile) return
        setStudentBatchError(null)
        setIsStudentBatchBusy(true)
        try {
            const updatedClass = await importStudents(
                classForImport.id,
                importFile
            )
            setClasses((current) =>
                current.map((item) =>
                    item.id === updatedClass.id ? updatedClass : item
                )
            )
            setClassForImport(null)
            setImportFile(null)
        } catch (caughtError) {
            setStudentBatchError(
                caughtError instanceof ApiError && caughtError.status === 409
                    ? t("students-import-duplicate-error")
                    : t("students-import-error")
            )
        } finally {
            setIsStudentBatchBusy(false)
            if (importInputRef.current) importInputRef.current.value = ""
        }
    }

    useEffect(() => {
        let isActive = true
        getStudentClasses(page, classFilter.trim(), gradeLevelFilter)
            .then((result) => {
                if (!isActive) return
                setClasses(result.items)
                setTotalPages(result.totalPages)
                if (result.page > result.totalPages) setPage(result.totalPages)
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
    }, [classFilter, gradeLevelFilter, page, reloadKey, t])

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
            setNewGradeLevel("")
            setIsAddingGradeLevel(false)
            setEditingClass(null)
            onCreateDialogOpenChange(false)
            setPage(1)
            setReloadKey((current) => current + 1)
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

    async function addGradeLevel(): Promise<void> {
        const normalizedLevel = newGradeLevel.trim()
        if (!normalizedLevel) return
        setClassError(null)
        try {
            const created = await onCreateGradeLevel(normalizedLevel)
            setGradeLevel(created.name)
            setNewGradeLevel("")
            setIsAddingGradeLevel(false)
        } catch {
            setClassError(t("grade-level-create-error"))
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
                setReloadKey((current) => current + 1)
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
            <StudentClassesList
                classes={classes}
                filteredClasses={filteredClasses}
                gradeLevels={gradeLevels}
                isLoading={isLoading}
                loadError={loadError}
                classFilter={classFilter}
                gradeLevelFilter={gradeLevelFilter}
                onClassFilterChange={(value) => {
                    setClassFilter(value)
                    setPage(1)
                }}
                onGradeLevelFilterChange={(value) => {
                    setGradeLevelFilter(value)
                    setPage(1)
                }}
                onManageClass={setManagedClassId}
                page={page}
                totalPages={totalPages}
                onPageChange={setPage}
            />

            <ManagedClassDialog
                studentClass={managedClass}
                isBatchBusy={isStudentBatchBusy}
                batchError={studentBatchError}
                isImportOpen={classForImport !== null}
                onClose={() => setManagedClassId(null)}
                onEditClass={(studentClass) => {
                    setEditingClass(studentClass)
                    setClassName(studentClass.name)
                    setGradeLevel(studentClass.grade_level)
                    setClassError(null)
                    setManagedClassId(null)
                }}
                onAddStudent={(studentClass) => {
                    setStudentError(null)
                    setClassForStudent(studentClass)
                }}
                onImport={(studentClass) => {
                    setStudentBatchError(null)
                    setImportFile(null)
                    setClassForImport(studentClass)
                }}
                onExport={(studentClass) =>
                    void handleExportStudents(studentClass)
                }
                onDeleteClass={setClassToDelete}
                onEditStudent={(studentClass, student) => {
                    setClassForStudent(studentClass)
                    setEditingStudent(student)
                    const [firstName, ...lastName] =
                        student.display_name.split(" ")
                    setStudentFirstName(firstName)
                    setStudentLastName(lastName.join(" "))
                    setStudentError(null)
                }}
                onDeleteStudent={setStudentToDelete}
            />

            <ImportStudentsDialog
                studentClass={classForImport}
                file={importFile}
                inputRef={importInputRef}
                isBusy={isStudentBatchBusy}
                error={studentBatchError}
                onFileChange={setImportFile}
                onClose={() => {
                    setClassForImport(null)
                    setImportFile(null)
                    setStudentBatchError(null)
                }}
                onSubmit={handleImportStudents}
            />

            <ClassFormDialog
                open={isCreateDialogOpen || editingClass !== null}
                editingClass={editingClass}
                classes={classes}
                gradeLevels={gradeLevels}
                className={className}
                gradeLevel={gradeLevel}
                newGradeLevel={newGradeLevel}
                isAddingGradeLevel={isAddingGradeLevel}
                isBusy={isCreatingClass}
                error={classError}
                onClassNameChange={setClassName}
                onGradeLevelChange={setGradeLevel}
                onNewGradeLevelChange={setNewGradeLevel}
                onAddingGradeLevelChange={setIsAddingGradeLevel}
                onDeleteGradeLevel={async (level) => {
                    setClassError(null)
                    try {
                        await onDeleteGradeLevel(level)
                    } catch (error) {
                        setClassError(
                            error instanceof ApiError && error.status === 409
                                ? t("grade-level-in-use-error")
                                : t("grade-level-delete-error")
                        )
                        throw error
                    }
                }}
                onAddGradeLevel={() => void addGradeLevel()}
                onClose={() => {
                    setEditingClass(null)
                    setClassName("")
                    setGradeLevel("")
                    setNewGradeLevel("")
                    setIsAddingGradeLevel(false)
                    setClassError(null)
                    onCreateDialogOpenChange(false)
                }}
                onSubmit={handleCreateClass}
            />

            <StudentFormDialog
                studentClass={classForStudent}
                editingStudent={editingStudent}
                firstName={studentFirstName}
                lastName={studentLastName}
                isBusy={isCreatingStudent}
                error={studentError}
                onFirstNameChange={setStudentFirstName}
                onLastNameChange={setStudentLastName}
                onClose={() => {
                    setClassForStudent(null)
                    setEditingStudent(null)
                    setStudentFirstName("")
                    setStudentLastName("")
                    setStudentError(null)
                }}
                onSubmit={handleCreateStudent}
            />

            <DeleteClassMemberDialog
                studentClass={classToDelete}
                student={studentToDelete}
                isBusy={isDeleting}
                error={deleteError}
                onClose={() => {
                    setClassToDelete(null)
                    setStudentToDelete(null)
                    setDeleteError(null)
                }}
                onConfirm={() => void handleDelete()}
            />
        </div>
    )
}

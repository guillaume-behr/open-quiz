import { request, requestBlob, requestPage } from "./client"
import type { Page, Student, StudentClass } from "./types"

export function getStudentClasses(
    page = 1,
    search = "",
    gradeLevel = "",
    pageSize = 8
): Promise<Page<StudentClass>> {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    })
    if (search) params.set("search", search)
    if (gradeLevel) params.set("grade_level", gradeLevel)
    return requestPage<StudentClass>(`/api/classes?${params}`)
}

export async function getAllStudentClasses(): Promise<StudentClass[]> {
    const first = await getStudentClasses(1, "", "", 100)
    const remaining = await Promise.all(
        Array.from({ length: first.totalPages - 1 }, (_, index) =>
            getStudentClasses(index + 2, "", "", 100)
        )
    )
    return [first, ...remaining].flatMap((result) => result.items)
}

export function createStudentClass(
    name: string,
    gradeLevel: string
): Promise<StudentClass> {
    return request<StudentClass>("/api/classes", {
        method: "POST",
        body: JSON.stringify({ name, grade_level: gradeLevel }),
    })
}

export function deleteStudentClass(classId: number): Promise<void> {
    return request<void>(`/api/classes/${classId}`, { method: "DELETE" })
}

export function updateStudentClass(
    classId: number,
    name: string,
    gradeLevel: string
): Promise<StudentClass> {
    return request<StudentClass>(`/api/classes/${classId}/update`, {
        method: "POST",
        body: JSON.stringify({ name, grade_level: gradeLevel }),
    })
}

export function createStudent(
    classId: number,
    displayName: string
): Promise<Student> {
    return request<Student>(`/api/classes/${classId}/students`, {
        method: "POST",
        body: JSON.stringify({ display_name: displayName }),
    })
}

export function deleteStudent(studentId: number): Promise<void> {
    return request<void>(`/api/classes/students/${studentId}`, {
        method: "DELETE",
    })
}

export function updateStudent(
    studentId: number,
    displayName: string
): Promise<Student> {
    return request<Student>(`/api/classes/students/${studentId}/update`, {
        method: "POST",
        body: JSON.stringify({ display_name: displayName }),
    })
}

export function downloadStudents(classId: number): Promise<Blob> {
    return requestBlob(`/api/classes/${classId}/students/export`)
}

export async function importStudents(
    classId: number,
    file: File
): Promise<StudentClass> {
    const payload: unknown = JSON.parse(await file.text())
    return request<StudentClass>(`/api/classes/${classId}/students/import`, {
        method: "POST",
        body: JSON.stringify(payload),
    })
}

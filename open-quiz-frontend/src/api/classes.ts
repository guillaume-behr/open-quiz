import { request } from "./client"
import type { Student, StudentClass } from "./types"

export function getStudentClasses(): Promise<StudentClass[]> {
    return request<StudentClass[]>("/api/classes")
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

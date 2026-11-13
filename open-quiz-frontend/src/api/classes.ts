import { PAGE_SIZE } from "@/lib/utils"

import { request, requestBlob, requestPage } from "./client"
import { ALL_PAGES_SIZE, fetchAllPages } from "./pagination"
import type { GradeLevel, Page, StudentClass } from "./types"

export function getStudentClasses(
    page = 1,
    search = "",
    gradeLevel = "",
    pageSize = PAGE_SIZE,
    signal?: AbortSignal
): Promise<Page<StudentClass>> {
    const params = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
    })
    if (search) params.set("search", search)
    if (gradeLevel) params.set("grade_level", gradeLevel)
    return requestPage<StudentClass>(`/api/classes?${params}`, { signal })
}

export function getAllStudentClasses(): Promise<StudentClass[]> {
    return fetchAllPages((page) =>
        getStudentClasses(page, "", "", ALL_PAGES_SIZE)
    )
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

export function importStudentClasses(
    payload: unknown
): Promise<{ class_count: number; student_count: number }> {
    return request("/api/classes/import", {
        method: "POST",
        body: JSON.stringify(payload),
    })
}

export function downloadClassImportExample(): Promise<Blob> {
    return requestBlob("/api/classes/example")
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

export function assignStudentAccount(
    classId: number,
    accountId: number
): Promise<StudentClass> {
    return request<StudentClass>(
        `/api/classes/${classId}/accounts/${accountId}`,
        { method: "POST" }
    )
}

export function unassignStudentAccount(
    classId: number,
    accountId: number
): Promise<void> {
    return request<void>(`/api/classes/${classId}/accounts/${accountId}`, {
        method: "DELETE",
    })
}

export function getGradeLevels(): Promise<GradeLevel[]> {
    return request<GradeLevel[]>("/api/classes/grade-levels")
}

export function createGradeLevel(name: string): Promise<GradeLevel> {
    return request<GradeLevel>("/api/classes/grade-levels", {
        method: "POST",
        body: JSON.stringify({ name }),
    })
}

export function deleteGradeLevel(id: number): Promise<void> {
    return request<void>(`/api/classes/grade-levels/${id}`, {
        method: "DELETE",
    })
}

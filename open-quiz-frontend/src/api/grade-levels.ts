import { request } from "@/api/client"
import type { GradeLevel } from "@/api/types"

export function getGradeLevels(): Promise<GradeLevel[]> {
    return request<GradeLevel[]>("/api/grade-levels")
}

export function createGradeLevel(name: string): Promise<GradeLevel> {
    return request<GradeLevel>("/api/grade-levels", {
        method: "POST",
        body: JSON.stringify({ name }),
    })
}

export function deleteGradeLevel(id: number): Promise<void> {
    return request<void>(`/api/grade-levels/${id}`, { method: "DELETE" })
}

import { request } from "./client"
import type { ProblemReport } from "./types"

export function createProblemReport(
    message: string,
    pagePath: string
): Promise<ProblemReport> {
    return request<ProblemReport>(
        "/api/problem-reports",
        {
            method: "POST",
            body: JSON.stringify({
                message,
                page_path: pagePath,
            }),
        },
        false
    )
}

export function getProblemReports(): Promise<ProblemReport[]> {
    return request<ProblemReport[]>("/api/problem-reports")
}

export function deleteProblemReport(reportId: number): Promise<void> {
    return request<void>(`/api/problem-reports/${reportId}`, {
        method: "DELETE",
    })
}

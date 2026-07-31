import { request, requestPage } from "./client"
import type { Page, ProblemReport } from "./types"

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

export function getProblemReports(page = 1): Promise<Page<ProblemReport>> {
    return requestPage<ProblemReport>(
        `/api/problem-reports?page=${page}&page_size=8`
    )
}

export function deleteProblemReport(reportId: number): Promise<void> {
    return request<void>(`/api/problem-reports/${reportId}`, {
        method: "DELETE",
    })
}

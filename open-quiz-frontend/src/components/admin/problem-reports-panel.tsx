import { deleteProblemReport } from "@/api/problem-reports"
import type { ProblemReport } from "@/api/types"
import { Button } from "@/components/ui/button"
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog"
import { ListStatus } from "@/components/ui/list-status"
import { Pagination } from "@/components/ui/pagination"
import { useAsyncAction } from "@/hooks/use-async-action"
import { apiErrorMessage } from "@/lib/errors"
import { Inbox, LoaderCircle, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

export function ProblemReportsPanel({
    isLoading,
    loadError,
    onRetry,
    reports,
    onDeleted,
    page,
    totalPages,
    total,
    onPageChange,
}: {
    /** True until the list has loaded once. */
    isLoading: boolean
    loadError: string | null
    onRetry: () => void
    reports: ProblemReport[]
    onDeleted: (reportId: number) => void
    page: number
    totalPages: number
    total: number
    onPageChange: (page: number) => void
}) {
    const { t, i18n } = useTranslation()
    const [reportToDelete, setReportToDelete] = useState<ProblemReport | null>(
        null
    )
    const dateFormatter = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        dateStyle: "medium",
        timeStyle: "short",
    })

    const deletion = useAsyncAction(
        async (report: ProblemReport) => {
            await deleteProblemReport(report.id)
            setReportToDelete(null)
            onDeleted(report.id)
        },
        (caught) => apiErrorMessage(caught, t, t("delete-problem-report-error"))
    )
    const deletingId = deletion.isPending ? reportToDelete?.id : undefined

    function openDeletion(report: ProblemReport | null) {
        deletion.setError(null)
        setReportToDelete(report)
    }

    const content =
        reports.length === 0 ? (
            <section className="flex flex-1 flex-col items-center justify-center rounded-2xl border bg-card p-8 text-center shadow-sm">
                <Inbox
                    className="mb-3 size-10 text-muted-foreground"
                    aria-hidden="true"
                />
                <h2 className="text-xl font-bold">{t("no-problem-reports")}</h2>
                <p className="mt-1 max-w-md text-sm text-muted-foreground">
                    {t("no-problem-reports-help")}
                </p>
            </section>
        ) : (
            <section aria-label={t("problem-reports")}>
                <div className="mb-4">
                    <p className="text-sm text-muted-foreground">
                        {t("problem-report-count", { count: total })}
                    </p>
                </div>
                <div
                    key={reports.map((report) => report.id).join(",")}
                    className="grid animate-in gap-4 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none"
                >
                    {reports.map((report) => (
                        <article
                            key={report.id}
                            className="rounded-2xl border bg-card p-4 shadow-sm sm:p-5"
                        >
                            <div className="flex flex-wrap items-start justify-between gap-3">
                                <dl className="flex flex-wrap gap-x-5 gap-y-1 text-xs text-muted-foreground">
                                    <div>
                                        <dt className="inline font-semibold">
                                            {t("reported-page")} :
                                        </dt>{" "}
                                        <dd className="inline font-mono">
                                            {report.page_path}
                                        </dd>
                                    </div>
                                    <div>
                                        <dt className="inline font-semibold">
                                            {t("reported-at")} :
                                        </dt>{" "}
                                        <dd className="inline">
                                            {dateFormatter.format(
                                                new Date(report.created_at)
                                            )}
                                        </dd>
                                    </div>
                                </dl>
                                <Button
                                    size="sm"
                                    variant="destructive"
                                    disabled={deletion.isPending}
                                    onClick={() => openDeletion(report)}
                                >
                                    {deletingId === report.id ? (
                                        <LoaderCircle
                                            className="animate-spin motion-reduce:animate-none"
                                            aria-hidden="true"
                                        />
                                    ) : (
                                        <Trash2 aria-hidden="true" />
                                    )}
                                    {t("delete-problem-report")}
                                </Button>
                            </div>
                            <p className="mt-4 leading-7 whitespace-pre-wrap">
                                {report.message}
                            </p>
                        </article>
                    ))}
                </div>
                <Pagination
                    currentPage={page}
                    totalPages={totalPages}
                    onPageChange={onPageChange}
                />
            </section>
        )

    return (
        <>
            <ListStatus
                isLoading={isLoading}
                error={loadError}
                onRetry={onRetry}
            >
                {content}
            </ListStatus>
            <ConfirmDeleteDialog
                open={reportToDelete !== null}
                title={t("delete-problem-report")}
                description={t("delete-problem-report-confirmation")}
                confirmLabel={t("delete-problem-report")}
                isBusy={deletion.isPending}
                error={deletion.error}
                onClose={() => openDeletion(null)}
                onConfirm={() =>
                    reportToDelete && void deletion.run(reportToDelete)
                }
            />
        </>
    )
}

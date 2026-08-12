import { deleteProblemReport } from "@/api/problem-reports"
import type { ProblemReport } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Pagination } from "@/components/ui/pagination"
import { errorMessage } from "@/lib/errors"
import { Inbox, LoaderCircle, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

export function ProblemReportsPanel({
    reports,
    onDeleted,
    page,
    totalPages,
    total,
    onPageChange,
}: {
    reports: ProblemReport[]
    onDeleted: (reportId: number) => void
    page: number
    totalPages: number
    total: number
    onPageChange: (page: number) => void
}) {
    const { t, i18n } = useTranslation()
    const [deletingId, setDeletingId] = useState<number | null>(null)
    const [reportToDelete, setReportToDelete] = useState<ProblemReport | null>(
        null
    )
    const [error, setError] = useState("")
    const dateFormatter = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        dateStyle: "medium",
        timeStyle: "short",
    })

    async function handleDelete() {
        if (!reportToDelete) return
        setError("")
        setDeletingId(reportToDelete.id)
        try {
            await deleteProblemReport(reportToDelete.id)
            const deletedId = reportToDelete.id
            setReportToDelete(null)
            onDeleted(deletedId)
        } catch (caught) {
            setError(errorMessage(caught, t("delete-problem-report-error")))
        } finally {
            setDeletingId(null)
        }
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
                {error && (
                    <p className="mb-4 text-sm text-destructive" role="alert">
                        {error}
                    </p>
                )}
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
                                    disabled={deletingId !== null}
                                    onClick={() => setReportToDelete(report)}
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
            {content}
            <Dialog
                open={reportToDelete !== null}
                onOpenChange={(open) => {
                    if (!open && deletingId === null) setReportToDelete(null)
                }}
                title={t("delete-problem-report")}
                description={t("delete-problem-report-confirmation")}
                size="sm"
            >
                <div className="flex justify-end gap-2">
                    <Button
                        variant="outline"
                        disabled={deletingId !== null}
                        onClick={() => setReportToDelete(null)}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        variant="destructive"
                        disabled={deletingId !== null}
                        onClick={() => void handleDelete()}
                    >
                        {deletingId !== null && (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        )}
                        {t("delete-problem-report")}
                    </Button>
                </div>
            </Dialog>
        </>
    )
}

import { deleteProblemReport } from "@/api/problem-reports"
import type { ProblemReport } from "@/api/types"
import { Button } from "@/components/ui/button"
import { errorMessage } from "@/lib/errors"
import { Inbox, LoaderCircle, Trash2 } from "lucide-react"
import { useState } from "react"
import { useTranslation } from "react-i18next"

export function ProblemReportsPanel({
    reports,
    onDeleted,
}: {
    reports: ProblemReport[]
    onDeleted: (reportId: number) => void
}) {
    const { t, i18n } = useTranslation()
    const [deletingId, setDeletingId] = useState<number | null>(null)
    const [error, setError] = useState("")
    const dateFormatter = new Intl.DateTimeFormat(i18n.resolvedLanguage, {
        dateStyle: "medium",
        timeStyle: "short",
    })

    async function handleDelete(report: ProblemReport) {
        if (!window.confirm(t("delete-problem-report-confirmation"))) return
        setError("")
        setDeletingId(report.id)
        try {
            await deleteProblemReport(report.id)
            onDeleted(report.id)
        } catch (caught) {
            setError(errorMessage(caught, t("delete-problem-report-error")))
        } finally {
            setDeletingId(null)
        }
    }

    if (reports.length === 0) {
        return (
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
        )
    }

    return (
        <section aria-labelledby="problem-reports-heading">
            <div className="mb-4">
                <h2 id="problem-reports-heading" className="text-xl font-bold">
                    {t("problem-reports")}
                </h2>
                <p className="text-sm text-muted-foreground">
                    {t("problem-report-count", { count: reports.length })}
                </p>
            </div>
            {error && (
                <p className="mb-4 text-sm text-destructive" role="alert">
                    {error}
                </p>
            )}
            <div className="grid gap-4">
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
                                onClick={() => void handleDelete(report)}
                            >
                                {deletingId === report.id ? (
                                    <LoaderCircle
                                        className="animate-spin"
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
        </section>
    )
}

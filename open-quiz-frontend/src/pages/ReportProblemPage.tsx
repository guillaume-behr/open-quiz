import { createProblemReport } from "@/api/problem-reports"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Textarea } from "@/components/ui/textarea"
import { errorMessage } from "@/lib/errors"
import { CircleCheck, LoaderCircle, MessageSquareWarning } from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, useLocation } from "react-router"

function sourcePath(state: unknown): string {
    if (
        typeof state === "object" &&
        state !== null &&
        "from" in state &&
        typeof state.from === "string" &&
        state.from.startsWith("/")
    ) {
        return state.from
    }
    return "/"
}

export function ReportProblemPage() {
    const { t } = useTranslation()
    const location = useLocation()
    const pagePath = sourcePath(location.state)
    const [isSending, setIsSending] = useState(false)
    const [error, setError] = useState("")
    const [sent, setSent] = useState(false)

    useEffect(() => {
        const previousTitle = document.title
        document.title = t("legal-page-browser-title", {
            title: t("signal"),
        })
        return () => {
            document.title = previousTitle
        }
    }, [t])

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        const form = event.currentTarget
        const data = new FormData(form)
        setError("")
        setSent(false)
        setIsSending(true)
        try {
            await createProblemReport(String(data.get("message")), pagePath)
            form.reset()
            setSent(true)
        } catch (caught) {
            setError(errorMessage(caught, t("problem-report-error")))
        } finally {
            setIsSending(false)
        }
    }

    return (
        <div className="mx-auto flex w-full max-w-2xl flex-1 items-center px-4 py-8 sm:px-8">
            <section className="w-full rounded-2xl border bg-card p-5 shadow-sm sm:p-8">
                <div className="mb-6 flex items-start gap-3">
                    <div className="rounded-xl bg-primary/10 p-2 text-primary">
                        <MessageSquareWarning aria-hidden="true" />
                    </div>
                    <div>
                        <h1 className="text-2xl font-extrabold">
                            {t("signal")}
                        </h1>
                        <p className="mt-1 text-sm leading-6 text-muted-foreground">
                            {t("problem-report-description")}
                        </p>
                    </div>
                </div>

                <form className="space-y-5" onSubmit={handleSubmit}>
                    <Field>
                        <FieldLabel htmlFor="problem-message">
                            {t("problem-report-message")}
                        </FieldLabel>
                        <Textarea
                            id="problem-message"
                            name="message"
                            required
                            minLength={5}
                            maxLength={2000}
                            rows={7}
                            placeholder={t("problem-report-placeholder")}
                        />
                        <p className="text-xs leading-5 text-muted-foreground">
                            {t("problem-report-privacy")}
                        </p>
                    </Field>

                    <div className="rounded-lg bg-muted p-3 text-sm">
                        <span className="font-semibold">
                            {t("problem-report-page")} :
                        </span>{" "}
                        <span className="font-mono">{pagePath}</span>
                    </div>

                    {error && (
                        <p className="text-sm text-destructive" role="alert">
                            {error}
                        </p>
                    )}
                    {sent && (
                        <p
                            className="flex items-center gap-2 text-sm font-medium text-green-700 dark:text-green-400"
                            role="status"
                        >
                            <CircleCheck aria-hidden="true" />
                            {t("problem-report-success")}
                        </p>
                    )}

                    <div className="flex flex-wrap items-center justify-between gap-3">
                        <Button
                            variant="outline"
                            nativeButton={false}
                            render={<Link to="/" />}
                        >
                            {t("back-home")}
                        </Button>
                        <Button type="submit" disabled={isSending}>
                            {isSending ? (
                                <LoaderCircle
                                    className="animate-spin"
                                    aria-hidden="true"
                                />
                            ) : (
                                <MessageSquareWarning aria-hidden="true" />
                            )}
                            {t(
                                isSending
                                    ? "sending-problem-report"
                                    : "send-problem-report"
                            )}
                        </Button>
                    </div>
                </form>
            </section>
        </div>
    )
}

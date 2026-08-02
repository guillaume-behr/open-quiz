import { Button } from "@/components/ui/button"
import { FileQuestion, MessageSquareWarning } from "lucide-react"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Link, useLocation } from "react-router"

export function NotFoundPage() {
    const { t } = useTranslation()
    const location = useLocation()

    useEffect(() => {
        document.title = t("legal-page-browser-title", {
            title: t("not-found-title"),
        })
    }, [t])

    return (
        <div className="mx-auto flex w-full max-w-2xl flex-1 items-center px-4 py-8 sm:px-8">
            <section className="w-full rounded-2xl border bg-card p-6 text-center shadow-sm sm:p-10">
                <div className="mx-auto flex size-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
                    <FileQuestion aria-hidden="true" className="size-8" />
                </div>
                <p className="mt-5 text-sm font-bold tracking-widest text-primary uppercase">
                    404
                </p>
                <h1 className="mt-1 text-2xl font-extrabold">
                    {t("not-found-title")}
                </h1>
                <p className="mt-2 leading-7 text-muted-foreground">
                    {t("not-found-description")}
                </p>
                <p className="mt-4 truncate rounded-lg bg-muted px-3 py-2 font-mono text-sm">
                    {location.pathname}
                </p>
                <div className="mt-7 flex flex-wrap justify-center gap-3">
                    <Button
                        nativeButton={false}
                        render={<Link to="/student/login" />}
                    >
                        {t("back-home")}
                    </Button>
                    <Button
                        variant="outline"
                        nativeButton={false}
                        render={
                            <Link
                                to="/report-a-problem"
                                state={{ from: location.pathname }}
                            />
                        }
                    >
                        <MessageSquareWarning aria-hidden="true" />
                        {t("signal")}
                    </Button>
                </div>
            </section>
        </div>
    )
}

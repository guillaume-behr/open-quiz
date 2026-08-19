import { Button } from "@/components/ui/button"
import { CircleAlert, MessageSquareWarning, RotateCcw } from "lucide-react"
import { Component, type ErrorInfo, type ReactNode, useEffect } from "react"
import { useTranslation } from "react-i18next"
import { Link, useLocation } from "react-router"

type ErrorBoundaryState = {
    hasError: boolean
}

const MODULE_RELOAD_STORAGE_KEY = "open-quiz-module-reload-at"
const MODULE_RELOAD_COOLDOWN_MS = 60_000
const MODULE_LOAD_ERROR_PATTERN =
    /dynamically imported module|MIME type|Failed to fetch dynamically/i

function isModuleLoadError(error: unknown): boolean {
    return (
        error instanceof Error && MODULE_LOAD_ERROR_PATTERN.test(error.message)
    )
}

function reloadForStaleBuild(): void {
    const lastReload = Number(
        window.sessionStorage.getItem(MODULE_RELOAD_STORAGE_KEY) ?? 0
    )
    if (Date.now() - lastReload < MODULE_RELOAD_COOLDOWN_MS) return
    window.sessionStorage.setItem(MODULE_RELOAD_STORAGE_KEY, String(Date.now()))
    window.location.reload()
}

class ErrorBoundary extends Component<
    { children: ReactNode },
    ErrorBoundaryState
> {
    state: ErrorBoundaryState = { hasError: false }

    static getDerivedStateFromError(): ErrorBoundaryState {
        return { hasError: true }
    }

    componentDidCatch(error: Error, info: ErrorInfo) {
        console.error("Uncaught application error", error, info.componentStack)
        if (isModuleLoadError(error)) {
            // Stale tab across a deploy: the server no longer serves the
            // hashed assets this page requested. A fresh load picks up the
            // current build.
            reloadForStaleBuild()
        }
    }

    render() {
        return this.state.hasError ? <ErrorBoundaryPage /> : this.props.children
    }
}

export function RouteErrorBoundary({ children }: { children: ReactNode }) {
    const location = useLocation()

    return <ErrorBoundary key={location.key}>{children}</ErrorBoundary>
}

function ErrorBoundaryPage() {
    const { t } = useTranslation()
    const location = useLocation()

    useEffect(() => {
        document.title = t("legal-page-browser-title", {
            title: t("error-page-title"),
        })
    }, [t])

    return (
        <main className="flex min-h-dvh items-center justify-center px-4 py-10">
            <section className="w-full max-w-xl rounded-2xl border bg-card p-6 text-center shadow-sm sm:p-10">
                <div className="mx-auto flex size-12 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
                    <CircleAlert aria-hidden="true" className="size-7" />
                </div>
                <h1 className="mt-5 text-2xl font-extrabold">
                    {t("error-page-title")}
                </h1>
                <p className="mt-2 leading-7 text-muted-foreground">
                    {t("error-page-description")}
                </p>
                <div className="mt-7 flex flex-wrap justify-center gap-3">
                    <Button
                        type="button"
                        onClick={() => window.location.reload()}
                    >
                        <RotateCcw aria-hidden="true" />
                        {t("error-page-retry")}
                    </Button>
                    <Link
                        to="/report-a-problem"
                        state={{ from: location.pathname }}
                        className="inline-flex h-9 items-center justify-center gap-2 rounded-lg border bg-background px-4 text-sm font-medium shadow-xs transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                    >
                        <MessageSquareWarning
                            aria-hidden="true"
                            className="size-4"
                        />
                        {t("signal")}
                    </Link>
                </div>
            </section>
        </main>
    )
}

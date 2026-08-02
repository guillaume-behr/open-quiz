import { LanguageSelector } from "@/components/language/language-selector"
import { PageTransition } from "@/components/navigation/page-transition"
import { ThemeSelector } from "@/components/theme/theme-selector"
import { useTranslation } from "react-i18next"
import { Link, Outlet, useLocation } from "react-router"

export function MainLayout() {
    const { t } = useTranslation()
    const location = useLocation()
    const isExamRoute = location.pathname === "/student/exam"

    const link = location.pathname.startsWith("/teacher")
        ? { text: "homepage", url: "/student/login" }
        : location.pathname.startsWith("/student")
          ? { text: "professor-space", url: "/teacher/login" }
          : { text: "homepage", url: "/student/login" }

    return (
        <div className="flex min-h-dvh flex-col items-center">
            <a
                href="#contenu"
                className="fixed top-2 left-2 z-[100] -translate-y-20 rounded-md bg-background px-4 py-2 font-bold text-foreground shadow-lg transition-transform focus:translate-y-0 focus:ring-3 focus:ring-ring/50 focus:outline-none"
            >
                {t("skip-to-content")}
            </a>
            {!isExamRoute && (
                <header className="flex w-full shrink-0 items-center justify-between gap-4 px-4 py-4 sm:px-10">
                    <Link
                        to="/student/login"
                        className="shrink-0 text-2xl font-extrabold text-primary transition-opacity hover:opacity-80 focus-visible:rounded focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none sm:text-3xl"
                    >
                        {t("app-name")}
                    </Link>
                    <Link
                        to={link.url}
                        className="max-w-[60%] text-end text-sm leading-tight font-bold text-primary underline underline-offset-4 sm:text-base"
                    >
                        {t(link.text)}
                    </Link>
                </header>
            )}

            <main
                id="contenu"
                tabIndex={-1}
                className="flex min-h-0 w-full flex-1"
            >
                <PageTransition>
                    <Outlet />
                </PageTransition>
            </main>

            {!isExamRoute && (
                <footer className="mt-3 flex w-full shrink-0 flex-wrap items-center justify-center gap-x-5 gap-y-3 bg-sidebar-primary px-4 py-3 text-sidebar-foreground sm:justify-between sm:px-10">
                    <div className="flex shrink-0 items-center gap-3">
                        <p className="text-sm whitespace-nowrap">
                            {t("app-version", { version: "2026.01" })}
                        </p>
                        <LanguageSelector />
                        <ThemeSelector />
                    </div>
                    <nav className="flex flex-wrap items-center justify-center gap-x-4 gap-y-2">
                        <Link className="text-sm underline" to="/legal-notice">
                            {t("legal")}
                        </Link>
                        <Link className="text-sm underline" to="/privacy">
                            {t("privacy")}
                        </Link>
                        <Link className="text-sm underline" to="/accessibility">
                            {t("accessibility-status")}
                        </Link>
                        <Link
                            className="text-sm underline"
                            to="/cookie-settings"
                        >
                            {t("cookies")}
                        </Link>
                        <Link
                            className="text-sm underline"
                            to="/report-a-problem"
                            state={{ from: location.pathname }}
                        >
                            {t("signal")}
                        </Link>
                    </nav>
                </footer>
            )}
        </div>
    )
}

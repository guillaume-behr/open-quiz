import { restoreSession, type User } from "@/api/api"
import { LanguageSelector } from "@/components/langage/langage-selector"
import { ThemeSelector } from "@/components/theme/theme-selector"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, Outlet, useLocation } from "react-router"

export function MainLayout() {
    const { t } = useTranslation()
    const location = useLocation()
    const [currentUser, setCurrentUser] = useState<User | null>(null)

    useEffect(() => {
        if (location.pathname !== "/") return

        restoreSession()
            .then(setCurrentUser)
            .catch(() => setCurrentUser(null))
    }, [location.pathname])

    const link =
        location.pathname === "/"
            ? currentUser?.is_admin
                ? { text: "administration", url: "/admin/dashboard" }
                : { text: "professor-space", url: "/dashboard" }
            : { text: "homepage", url: "/" }

    return (
        <div className="flex h-screen flex-col items-center justify-between">
            <header className="flex h-1/15 w-full items-center justify-between px-10">
                <p className="text-3xl font-extrabold text-primary">
                    {t("app-name")}
                </p>
                <Link
                    to={link.url}
                    className="cursor-pointer font-bold text-primary underline"
                >
                    {t(link.text)}
                </Link>
            </header>

            <main className="flex min-h-0 w-full flex-1">
                <Outlet />
            </main>

            <div className="absolute right-1 bottom-1/18 flex flex-col gap-1">
                <LanguageSelector />
                <ThemeSelector />
            </div>

            <footer className="flex h-1/20 w-full items-center justify-between bg-sidebar-primary px-10">
                <p className="text-sm">v 2026.01</p>
                <div className="flex items-center gap-4">
                    <Link className="cursor-pointer text-sm underline" to="">
                        {t("legal")}
                    </Link>
                    <Link className="cursor-pointer text-sm underline" to="">
                        {t("privacy")}
                    </Link>
                    <Link className="cursor-pointer text-sm underline" to="">
                        {t("accessibility")}
                    </Link>
                    <Link className="cursor-pointer text-sm underline" to="">
                        {t("cookies")}
                    </Link>
                    <Link className="cursor-pointer text-sm underline" to="">
                        {t("signal")}
                    </Link>
                </div>
            </footer>
        </div>
    )
}

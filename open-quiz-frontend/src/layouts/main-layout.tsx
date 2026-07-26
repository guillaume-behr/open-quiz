import { LanguageSelector } from "@/components/langage/langage-selector"
import { ThemeSelector } from "@/components/theme/theme-selector"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { Link, Outlet, useLocation } from "react-router"

export function MainLayout() {
    const { t } = useTranslation()

    const [link, setLink] = useState({
        text: "",
        url: "",
    })

    const location = useLocation()
    useEffect(() => {
        switch (location.pathname) {
            case "/":
                setLink({ text: "professor-space", url: "/dashboard" })
                break
            case "/dashboard":
                setLink({ text: "homepage", url: "/" })
                break
        }
    }, [location])

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

            <LanguageSelector className="absolute right-12 bottom-1/13" />
            <ThemeSelector className="absolute right-2 bottom-1/13" />

            <footer className="flex h-1/15 w-full items-center justify-between bg-sidebar-primary px-10">
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

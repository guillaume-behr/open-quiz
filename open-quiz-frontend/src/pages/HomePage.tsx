import { JoinQuizForm } from "@/components/forms/join-quiz-form"
import { LanguageSelector } from "@/components/langage/langage-selector"
import { ThemeSelector } from "@/components/theme/theme-selector"
import { useTranslation } from "react-i18next"

export function HomePage() {
    const { t } = useTranslation()

    return (
        <div className="flex h-screen flex-col items-center justify-between">
            <header className="flex h-1/15 w-full items-center justify-between px-10">
                <p className="text-3xl font-extrabold text-primary">
                    {t("app-name")}
                </p>
                <a className="cursor-pointer font-bold text-primary underline" href="">
                    {t("professor-space")}
                </a>
            </header>

            <JoinQuizForm />

            <LanguageSelector className="absolute bottom-1/13 right-12"/>
            <ThemeSelector className="absolute bottom-1/13 right-2"/>
            
            <footer className="flex h-1/15 w-full items-center justify-between bg-sidebar-primary px-10">
                <p className="text-sm">© 2026 Open Quiz</p>
                <div className="flex items-center gap-4">
                    <a className="cursor-pointer text-sm underline" href="">
                        {t("legal")}
                    </a>
                    <a className="cursor-pointer text-sm underline" href="">
                        {t("privacy")}
                    </a>
                    <a className="cursor-pointer text-sm underline" href="">
                        {t("accessibility")}
                    </a>
                    <a className="cursor-pointer text-sm underline" href="">
                        {t("cookies")}
                    </a>
                    <a className="cursor-pointer text-sm underline" href="">
                        {t("signal")}
                    </a>
                </div>
            </footer>
        </div>
    )
}

export default HomePage

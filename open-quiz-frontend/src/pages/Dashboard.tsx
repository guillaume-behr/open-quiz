import { login, logout, restoreSession, type User } from "@/api/api"
import { DashboardLogin } from "@/components/forms/dashboard-login"
import { Button } from "@/components/ui/button"
import { LoaderCircle, LogOut } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

export function Dashboard() {
    const { t } = useTranslation()
    const [currentUser, setCurrentUser] = useState<User | null>(null)
    const [isLoading, setIsLoading] = useState(true)

    useEffect(() => {
        restoreSession()
            .then(setCurrentUser)
            .catch(() => setCurrentUser(null))
            .finally(() => setIsLoading(false))
    }, [])

    async function handleLogin(username: string, password: string) {
        setCurrentUser(await login(username, password))
    }

    function handleLogout() {
        void logout().finally(() => setCurrentUser(null))
    }

    if (isLoading) {
        return (
            <div className="flex flex-1 items-center justify-center">
                <LoaderCircle className="size-9 animate-spin text-primary" />
            </div>
        )
    }

    if (!currentUser) {
        return (
            <div className="flex flex-1 items-center justify-center px-4">
                <DashboardLogin onLogin={handleLogin} />
            </div>
        )
    }

    return (
        <div className="mx-auto flex w-full max-w-6xl flex-1 flex-col gap-6 overflow-y-auto px-6 py-8">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p className="text-sm font-medium text-primary">
                        {t("professor-space")}
                    </p>
                    <h1 className="text-3xl font-extrabold">
                        {t("welcome-professor", {
                            name: currentUser.display_name,
                        })}
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t("professor-dashboard-help")}
                    </p>
                </div>
                <Button variant="outline" onClick={handleLogout}>
                    <LogOut />
                    {t("sign-out")}
                </Button>
            </div>
        </div>
    )
}

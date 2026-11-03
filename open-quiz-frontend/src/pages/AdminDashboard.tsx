import { login, logout, restoreSession, verifyTwoFactor } from "@/api/auth"
import type { TwoFactorChallenge, User } from "@/api/types"
import { AdminWorkspace } from "@/components/admin/admin-workspace"
import { DashboardAuthentication } from "@/components/forms/dashboard-authentication"
import { PageLoader } from "@/components/ui/page-loader"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

async function requireAdmin(user: User, message: string): Promise<void> {
    if (!user.is_admin) {
        await logout()
        throw new Error(message)
    }
}

export function AdminDashboard() {
    const { t } = useTranslation()
    const [currentUser, setCurrentUser] = useState<User | null>(null)
    const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null)
    const [isLoading, setIsLoading] = useState(true)

    useEffect(() => {
        restoreSession()
            .then(async (user) => {
                await requireAdmin(user, t("admin-only"))
                setCurrentUser(user)
            })
            .catch(() => {
                setCurrentUser(null)
            })
            .finally(() => setIsLoading(false))
    }, [t])

    async function handleLogin(username: string, password: string) {
        const result = await login(username, password, "admin")
        if (result.status === "authenticated") {
            await completeSignIn(result.user)
            return
        }
        setChallenge(result)
    }

    async function handleTwoFactor(code: string) {
        if (!challenge) return
        await completeSignIn(
            await verifyTwoFactor(challenge.challenge_token, code)
        )
    }

    async function completeSignIn(user: User) {
        await requireAdmin(user, t("admin-only"))
        setCurrentUser(user)
        setChallenge(null)
    }

    function handleLogout() {
        void logout().finally(() => setCurrentUser(null))
    }

    if (isLoading) {
        return <PageLoader />
    }

    if (!currentUser) {
        return (
            <DashboardAuthentication
                challenge={challenge}
                title={t("admin-login")}
                instructions={t("admin-login-instructions")}
                onLogin={handleLogin}
                onVerify={handleTwoFactor}
                onCancelChallenge={() => setChallenge(null)}
            />
        )
    }

    return <AdminWorkspace currentUser={currentUser} onLogout={handleLogout} />
}

import { AdminWorkspace } from "@/components/admin/admin-workspace"
import { DashboardAuthentication } from "@/components/forms/dashboard-authentication"
import { PageLoader } from "@/components/ui/page-loader"
import { useStaffSession } from "@/hooks/use-staff-session"
import { useEffect } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

export function AdminDashboard() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const session = useStaffSession("admin")
    const { user } = session

    // A teacher who opens this page goes back to their own dashboard, still
    // signed in.
    useEffect(() => {
        if (user && !user.is_admin)
            navigate("/teacher/dashboard", { replace: true })
    }, [navigate, user])

    if (session.isLoading || (user && !user.is_admin)) {
        return <PageLoader />
    }

    if (!user) {
        return (
            <DashboardAuthentication
                challenge={session.challenge}
                title={t("admin-login")}
                instructions={t("admin-login-instructions")}
                notice={session.expired ? t("staff-session-expired") : null}
                onLogin={session.signIn}
                onVerify={session.completeTwoFactor}
                onCancelChallenge={session.cancelChallenge}
            />
        )
    }

    return (
        <AdminWorkspace
            currentUser={user}
            onLogout={() => void session.signOut()}
        />
    )
}

import {
    login,
    logout,
    restoreSession,
    verifyTwoFactor,
    type TwoFactorChallenge,
    type User,
} from "@/api/api"
import { DashboardLogin } from "@/components/forms/dashboard-login"
import { TwoFactorForm } from "@/components/forms/two-factor-form"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
    ChartColumn,
    ClipboardList,
    LoaderCircle,
    LogOut,
    UsersRound,
    type LucideIcon,
} from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

type DashboardSection = "students" | "quizzes" | "results"

type DashboardEntry = {
    id: DashboardSection
    icon: LucideIcon
    label: string
    description: string
}

export function Dashboard() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [currentUser, setCurrentUser] = useState<User | null>(null)
    const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [activeSection, setActiveSection] =
        useState<DashboardSection>("students")

    const dashboardEntries: DashboardEntry[] = [
        {
            id: "students",
            icon: UsersRound,
            label: t("students-and-classes"),
            description: t("students-and-classes-help"),
        },
        {
            id: "quizzes",
            icon: ClipboardList,
            label: t("quiz-management"),
            description: t("quiz-management-help"),
        },
        {
            id: "results",
            icon: ChartColumn,
            label: t("results"),
            description: t("results-help"),
        },
    ]

    const activeEntry =
        dashboardEntries.find((entry) => entry.id === activeSection) ??
        dashboardEntries[0]

    useEffect(() => {
        restoreSession()
            .then((user) => {
                if (user.is_admin) {
                    navigate("/admin/dashboard", { replace: true })
                    return
                }
                setCurrentUser(user)
            })
            .catch(() => setCurrentUser(null))
            .finally(() => setIsLoading(false))
    }, [navigate])

    async function handleLogin(username: string, password: string) {
        setChallenge(await login(username, password))
    }

    async function handleTwoFactor(code: string) {
        if (!challenge) return
        const user = await verifyTwoFactor(challenge.challenge_token, code)
        setChallenge(null)
        if (user.is_admin) {
            navigate("/admin/dashboard", { replace: true })
            return
        }
        setCurrentUser(user)
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
                {challenge ? (
                    <TwoFactorForm
                        challenge={challenge}
                        onVerify={handleTwoFactor}
                        onCancel={() => setChallenge(null)}
                    />
                ) : (
                    <DashboardLogin onLogin={handleLogin} />
                )}
            </div>
        )
    }

    return (
        <div className="flex w-full flex-1 flex-col gap-4 overflow-y-auto px-3 py-2 sm:px-4">
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

            <div className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
                <aside className="h-fit rounded-2xl border bg-card p-3 shadow-sm">
                    <p className="px-3 py-2 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                        {t("dashboard-menu")}
                    </p>
                    <nav
                        className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible"
                        aria-label={t("dashboard-menu")}
                    >
                        {dashboardEntries.map((entry) => {
                            const Icon = entry.icon
                            const isActive = entry.id === activeSection

                            return (
                                <button
                                    key={entry.id}
                                    type="button"
                                    onClick={() => setActiveSection(entry.id)}
                                    aria-current={isActive ? "page" : undefined}
                                    className={cn(
                                        "flex min-w-max items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-medium transition-colors lg:w-full lg:min-w-0",
                                        isActive
                                            ? "bg-primary text-primary-foreground shadow-sm"
                                            : "text-muted-foreground hover:bg-muted hover:text-foreground"
                                    )}
                                >
                                    <Icon className="size-5 shrink-0" />
                                    <span>{entry.label}</span>
                                </button>
                            )
                        })}
                    </nav>
                </aside>

                <section
                    className="min-h-72 rounded-2xl border bg-card p-4 shadow-sm sm:p-5"
                    aria-labelledby={`${activeEntry.id}-title`}
                >
                    <div className="flex items-start gap-4">
                        <div className="rounded-xl bg-primary/10 p-3 text-primary">
                            <activeEntry.icon className="size-6" />
                        </div>
                        <div>
                            <h2
                                id={`${activeEntry.id}-title`}
                                className="text-2xl font-bold"
                            >
                                {activeEntry.label}
                            </h2>
                            <p className="mt-1 text-sm text-muted-foreground">
                                {activeEntry.description}
                            </p>
                        </div>
                    </div>
                </section>
            </div>
        </div>
    )
}

import { login, logout, restoreSession, verifyTwoFactor } from "@/api/auth"
import {
    createGradeLevel,
    deleteGradeLevel,
    getGradeLevels,
} from "@/api/grade-levels"
import type { GradeLevel, TwoFactorChallenge, User } from "@/api/types"
import { DashboardLogin } from "@/components/forms/dashboard-login"
import { TwoFactorForm } from "@/components/forms/two-factor-form"
import { NavbarAction } from "@/components/navigation/navbar-action"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
    ChartColumn,
    ClipboardList,
    Download,
    Dumbbell,
    LibraryBig,
    LoaderCircle,
    LogOut,
    Plus,
    RotateCcw,
    School,
    UsersRound,
    type LucideIcon,
} from "lucide-react"
import { lazy, Suspense, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

type DashboardSection =
    | "students"
    | "classes"
    | "exam-quizzes"
    | "makeup"
    | "training-quizzes"
    | "question-banks"
    | "results"

const ClassesPanel = lazy(() =>
    import("@/components/classes/classes-panel").then((module) => ({
        default: module.ClassesPanel,
    }))
)
const QuestionBanksPanel = lazy(() =>
    import("@/components/question-banks/question-banks-panel").then(
        (module) => ({ default: module.QuestionBanksPanel })
    )
)
const QuizzesPanel = lazy(() =>
    import("@/components/quizzes/quizzes-panel").then((module) => ({
        default: module.QuizzesPanel,
    }))
)
const MakeupSessionsPanel = lazy(() =>
    import("@/components/quizzes/makeup-sessions-panel").then((module) => ({
        default: module.MakeupSessionsPanel,
    }))
)
const ResultsPanel = lazy(() =>
    import("@/components/results/results-panel").then((module) => ({
        default: module.ResultsPanel,
    }))
)
const StudentsPanel = lazy(() =>
    import("@/components/students/students-panel").then((module) => ({
        default: module.StudentsPanel,
    }))
)
const ClassTrainingBanksPanel = lazy(() =>
    import("@/components/training/class-training-banks-panel").then(
        (module) => ({ default: module.ClassTrainingBanksPanel })
    )
)

type DashboardEntry = {
    id: DashboardSection
    icon: LucideIcon
    label: string
    description: string
}

export function Dashboard({ page }: { page: "login" | "dashboard" }) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [currentUser, setCurrentUser] = useState<User | null>(null)
    const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [activeSection, setActiveSection] =
        useState<DashboardSection>("students")
    const [isQuestionBankCreationOpen, setIsQuestionBankCreationOpen] =
        useState(false)
    const [isQuizCreationOpen, setIsQuizCreationOpen] = useState(false)
    const [isClassCreationOpen, setIsClassCreationOpen] = useState(false)
    const [isStudentCreationOpen, setIsStudentCreationOpen] = useState(false)
    const [isResultsExportOpen, setIsResultsExportOpen] = useState(false)
    const [gradeLevels, setGradeLevels] = useState<GradeLevel[]>([])

    const dashboardEntries: DashboardEntry[] = [
        {
            id: "students",
            icon: UsersRound,
            label: t("students"),
            description: t("students-management-help"),
        },
        {
            id: "classes",
            icon: School,
            label: t("classes"),
            description: t("classes-management-help"),
        },
        {
            id: "exam-quizzes",
            icon: ClipboardList,
            label: t("exam-quizzes"),
            description: t("exam-quizzes-help"),
        },
        {
            id: "makeup",
            icon: RotateCcw,
            label: t("makeup-tab"),
            description: t("makeup-professor-help"),
        },
        {
            id: "training-quizzes",
            icon: Dumbbell,
            label: t("training-quizzes"),
            description: t("training-quizzes-help"),
        },
        {
            id: "question-banks",
            icon: LibraryBig,
            label: t("question-banks"),
            description: t("question-banks-help"),
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
                if (page === "login") {
                    navigate("/teacher/dashboard", { replace: true })
                    return
                }
                void getGradeLevels()
                    .then(setGradeLevels)
                    .catch(() => setGradeLevels([]))
            })
            .catch(() => {
                setCurrentUser(null)
                if (page === "dashboard")
                    navigate("/teacher/login", { replace: true })
            })
            .finally(() => setIsLoading(false))
    }, [navigate, page])

    useEffect(() => {
        const previousTitle = document.title
        document.title = `Open Quiz | ${t("professor-space")}`

        return () => {
            document.title = previousTitle
        }
    }, [t])

    async function handleLogin(username: string, password: string) {
        setChallenge(await login(username, password, "professor"))
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
        try {
            setGradeLevels(await getGradeLevels())
        } catch {
            // Authentication succeeded. A transient dashboard bootstrap failure
            // must not invalidate the consumed two-factor challenge.
            setGradeLevels([])
        }
        navigate("/teacher/dashboard", { replace: true })
    }

    function handleLogout() {
        void logout().finally(() => {
            setCurrentUser(null)
            setGradeLevels([])
            navigate("/teacher/login", { replace: true })
        })
    }

    async function handleCreateGradeLevel(name: string): Promise<GradeLevel> {
        const normalizedName = name.trim().replace(/\s+/g, " ")
        const existing = gradeLevels.find(
            (level) =>
                level.name.localeCompare(normalizedName, undefined, {
                    sensitivity: "accent",
                }) === 0
        )
        if (existing) return existing

        const level = await createGradeLevel(normalizedName)
        setGradeLevels((current) =>
            current.some((item) => item.id === level.id)
                ? current
                : [...current, level].sort((a, b) =>
                      a.name.localeCompare(b.name, "fr")
                  )
        )
        return level
    }

    async function handleDeleteGradeLevel(level: GradeLevel): Promise<void> {
        await deleteGradeLevel(level.id)
        setGradeLevels((current) =>
            current.filter((item) => item.id !== level.id)
        )
    }

    if (isLoading) {
        return (
            <div
                className="flex flex-1 items-center justify-center"
                role="status"
                aria-label={t("page-loading")}
            >
                <LoaderCircle className="size-9 animate-spin text-primary motion-reduce:animate-none" />
            </div>
        )
    }

    if (page === "login" && !currentUser) {
        return (
            <div className="flex flex-1 items-center justify-center px-4">
                {challenge ? (
                    <TwoFactorForm
                        challenge={challenge}
                        onVerify={handleTwoFactor}
                        onCancel={() => setChallenge(null)}
                    />
                ) : (
                    <DashboardLogin
                        onLogin={handleLogin}
                        title={t("professor-space")}
                    />
                )}
            </div>
        )
    }

    if (!currentUser) return null

    return (
        <div className="flex w-full flex-1 flex-col gap-4 overflow-y-auto px-4 py-2 sm:px-6 lg:px-10">
            <NavbarAction>
                <Button variant="outline" onClick={handleLogout}>
                    <LogOut />
                    {t("sign-out")}
                </Button>
            </NavbarAction>
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-extrabold">
                        {t("welcome-professor", {
                            name: currentUser.display_name,
                        })}
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t("professor-dashboard-help")}
                    </p>
                </div>
            </div>

            <div className="grid min-h-0 min-w-0 flex-1 items-start gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
                <aside className="h-fit min-w-0 rounded-2xl border bg-card p-3 shadow-sm">
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
                                        "flex min-w-max items-center gap-3 rounded-xl px-3 py-3 text-left text-sm font-medium transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none lg:w-full lg:min-w-0",
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
                    key={activeSection}
                    className="min-h-72 min-w-0 animate-in overflow-hidden rounded-2xl border bg-card p-4 shadow-sm duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none sm:p-5 lg:min-h-full"
                    aria-labelledby={`${activeEntry.id}-title`}
                >
                    <div className="flex flex-wrap items-start justify-between gap-4">
                        <div className="flex min-w-0 items-start gap-3 sm:gap-4">
                            <div className="rounded-xl bg-primary/10 p-3 text-primary">
                                <activeEntry.icon className="size-6" />
                            </div>
                            <div className="min-w-0">
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
                        {activeSection === "question-banks" && (
                            <Button
                                type="button"
                                onClick={() =>
                                    setIsQuestionBankCreationOpen(true)
                                }
                            >
                                <Plus />
                                {t("create-question-bank")}
                            </Button>
                        )}
                        {activeSection === "students" && (
                            <Button
                                type="button"
                                onClick={() => setIsStudentCreationOpen(true)}
                            >
                                <Plus />
                                {t("create-student-account")}
                            </Button>
                        )}
                        {activeSection === "classes" && (
                            <Button
                                type="button"
                                onClick={() => setIsClassCreationOpen(true)}
                            >
                                <Plus />
                                {t("create-class")}
                            </Button>
                        )}
                        {activeSection === "exam-quizzes" && (
                            <Button
                                type="button"
                                onClick={() => setIsQuizCreationOpen(true)}
                            >
                                <Plus />
                                {t("create-exam-quiz")}
                            </Button>
                        )}
                        {activeSection === "results" && (
                            <Button
                                type="button"
                                onClick={() => setIsResultsExportOpen(true)}
                            >
                                <Download />
                                {t("export-results-csv")}
                            </Button>
                        )}
                    </div>
                    <Suspense
                        fallback={
                            <div
                                className="flex min-h-64 items-center justify-center"
                                role="status"
                                aria-label={t("page-loading")}
                            >
                                <LoaderCircle className="size-8 animate-spin text-primary motion-reduce:animate-none" />
                            </div>
                        }
                    >
                        {activeSection === "question-banks" && (
                            <QuestionBanksPanel
                                gradeLevels={gradeLevels}
                                onCreateGradeLevel={handleCreateGradeLevel}
                                onDeleteGradeLevel={handleDeleteGradeLevel}
                                isCreateDialogOpen={isQuestionBankCreationOpen}
                                onCreateDialogOpenChange={
                                    setIsQuestionBankCreationOpen
                                }
                            />
                        )}
                        {activeSection === "students" && (
                            <StudentsPanel
                                isCreateDialogOpen={isStudentCreationOpen}
                                onCreateDialogOpenChange={
                                    setIsStudentCreationOpen
                                }
                            />
                        )}
                        {activeSection === "classes" && (
                            <ClassesPanel
                                gradeLevels={gradeLevels}
                                onCreateGradeLevel={handleCreateGradeLevel}
                                onDeleteGradeLevel={handleDeleteGradeLevel}
                                isCreateDialogOpen={isClassCreationOpen}
                                onCreateDialogOpenChange={
                                    setIsClassCreationOpen
                                }
                            />
                        )}
                        {activeSection === "exam-quizzes" && (
                            <QuizzesPanel
                                isCreateDialogOpen={isQuizCreationOpen}
                                onCreateDialogOpenChange={setIsQuizCreationOpen}
                                gradeLevels={gradeLevels}
                                onDeleteGradeLevel={handleDeleteGradeLevel}
                            />
                        )}
                        {activeSection === "makeup" && <MakeupSessionsPanel />}
                        {activeSection === "training-quizzes" && (
                            <ClassTrainingBanksPanel />
                        )}
                        {activeSection === "results" && (
                            <ResultsPanel
                                isExportDialogOpen={isResultsExportOpen}
                                onExportDialogOpenChange={
                                    setIsResultsExportOpen
                                }
                            />
                        )}
                    </Suspense>
                </section>
            </div>
        </div>
    )
}

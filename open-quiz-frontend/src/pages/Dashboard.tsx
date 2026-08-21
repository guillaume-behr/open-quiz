import { login, logout, restoreSession, verifyTwoFactor } from "@/api/auth"
import {
    createGradeLevel,
    deleteGradeLevel,
    getGradeLevels,
} from "@/api/grade-levels"
import type { GradeLevel, TwoFactorChallenge, User } from "@/api/types"
import { DashboardAuthentication } from "@/components/forms/dashboard-authentication"
import {
    DashboardShell,
    type DashboardEntry,
} from "@/components/navigation/dashboard-shell"
import { Button } from "@/components/ui/button"
import { PageLoader } from "@/components/ui/page-loader"
import {
    ChartColumn,
    ClipboardList,
    Download,
    Dumbbell,
    LibraryBig,
    Plus,
    RotateCcw,
    School,
    UsersRound,
} from "lucide-react"
import { lazy, useEffect, useState } from "react"
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

const defaultGradeLevelOrder = new Map([
    ["2nd", 0],
    ["1ere", 1],
    ["Tle", 2],
])

function compareGradeLevels(first: GradeLevel, second: GradeLevel): number {
    const firstOrder = defaultGradeLevelOrder.get(first.name) ?? 3
    const secondOrder = defaultGradeLevelOrder.get(second.name) ?? 3
    return (
        firstOrder - secondOrder || first.name.localeCompare(second.name, "fr")
    )
}

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

    const dashboardEntries: DashboardEntry<DashboardSection>[] = [
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
                : [...current, level].sort(compareGradeLevels)
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
        return <PageLoader />
    }

    if (page === "login" && !currentUser) {
        return (
            <DashboardAuthentication
                challenge={challenge}
                title={t("professor-space")}
                onLogin={handleLogin}
                onVerify={handleTwoFactor}
                onCancelChallenge={() => setChallenge(null)}
            />
        )
    }

    if (!currentUser) return null

    return (
        <DashboardShell
            entries={dashboardEntries}
            activeEntry={activeEntry}
            welcome={t("welcome-professor", {
                name: currentUser.display_name,
            })}
            help={t("professor-dashboard-help")}
            menuLabel={t("dashboard-menu")}
            navigationLabel={t("dashboard-menu")}
            signOutLabel={t("sign-out")}
            loadingLabel={t("page-loading")}
            onSelect={setActiveSection}
            onSignOut={handleLogout}
            headerAction={
                <>
                    {activeSection === "question-banks" && (
                        <Button
                            type="button"
                            onClick={() => setIsQuestionBankCreationOpen(true)}
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
                </>
            }
        >
            {activeSection === "question-banks" && (
                <QuestionBanksPanel
                    gradeLevels={gradeLevels}
                    onCreateGradeLevel={handleCreateGradeLevel}
                    onDeleteGradeLevel={handleDeleteGradeLevel}
                    isCreateDialogOpen={isQuestionBankCreationOpen}
                    onCreateDialogOpenChange={setIsQuestionBankCreationOpen}
                />
            )}
            {activeSection === "students" && (
                <StudentsPanel
                    isCreateDialogOpen={isStudentCreationOpen}
                    onCreateDialogOpenChange={setIsStudentCreationOpen}
                />
            )}
            {activeSection === "classes" && (
                <ClassesPanel
                    gradeLevels={gradeLevels}
                    onCreateGradeLevel={handleCreateGradeLevel}
                    onDeleteGradeLevel={handleDeleteGradeLevel}
                    isCreateDialogOpen={isClassCreationOpen}
                    onCreateDialogOpenChange={setIsClassCreationOpen}
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
                    onExportDialogOpenChange={setIsResultsExportOpen}
                />
            )}
        </DashboardShell>
    )
}

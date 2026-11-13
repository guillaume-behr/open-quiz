import { usePageTitle } from "@/hooks/use-page-title"
import { useSectionParam } from "@/hooks/use-section-param"
import {
    createGradeLevel,
    deleteGradeLevel,
    getGradeLevels,
} from "@/api/classes"
import type { GradeLevel } from "@/api/types"
import { DashboardAuthentication } from "@/components/forms/dashboard-authentication"
import {
    DashboardShell,
    type DashboardEntry,
} from "@/components/navigation/dashboard-shell"
import { Button } from "@/components/ui/button"
import { LoadErrorNotice } from "@/components/ui/list-status"
import { PageLoader } from "@/components/ui/page-loader"
import { useStaffSession } from "@/hooks/use-staff-session"
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

const dashboardSections = [
    "students",
    "classes",
    "exam-quizzes",
    "makeup",
    "training-quizzes",
    "question-banks",
    "results",
] as const

type DashboardSection = (typeof dashboardSections)[number]

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

export function TeacherPage({ page }: { page: "login" | "dashboard" }) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const session = useStaffSession("professor")
    const currentUser =
        session.user && !session.user.is_admin ? session.user : null
    const [activeSection, setActiveSection] = useSectionParam(dashboardSections)
    const [isQuestionBankCreationOpen, setIsQuestionBankCreationOpen] =
        useState(false)
    const [isQuizCreationOpen, setIsQuizCreationOpen] = useState(false)
    const [isClassCreationOpen, setIsClassCreationOpen] = useState(false)
    const [isStudentCreationOpen, setIsStudentCreationOpen] = useState(false)
    const [isResultsExportOpen, setIsResultsExportOpen] = useState(false)
    const [gradeLevels, setGradeLevels] = useState<GradeLevel[]>([])
    const [gradeLevelsFailed, setGradeLevelsFailed] = useState(false)
    const [gradeLevelsAttempt, setGradeLevelsAttempt] = useState(0)

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

    // Where the session sends this page: administrators to their own
    // dashboard, a signed-in teacher past the login form, and a signed-out
    // visitor (or an expired session) back to it.
    const signedInUser = session.user
    useEffect(() => {
        if (session.isLoading) return
        if (signedInUser?.is_admin) {
            void navigate("/admin/dashboard", { replace: true })
        } else if (signedInUser && page === "login") {
            void navigate("/teacher/dashboard", { replace: true })
        } else if (!signedInUser && page === "dashboard") {
            void navigate("/teacher/login", { replace: true })
        }
    }, [navigate, page, session.isLoading, signedInUser])

    const teacherId = currentUser?.id
    useEffect(() => {
        if (teacherId === undefined) return
        let active = true
        getGradeLevels()
            .then((levels) => {
                if (!active) return
                setGradeLevels(levels)
                setGradeLevelsFailed(false)
            })
            .catch(() => {
                // A transient failure leaves the list empty, not the session,
                // and says so: empty selects alone would look like no levels.
                if (!active) return
                setGradeLevels([])
                setGradeLevelsFailed(true)
            })
        return () => {
            active = false
        }
    }, [teacherId, gradeLevelsAttempt])

    usePageTitle(t("professor-space"))

    function handleLogout() {
        void session.signOut().finally(() => setGradeLevels([]))
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
        // Usable at once, then put where the API orders it: only the API
        // knows the collation that sorts levels.
        setGradeLevels((current) =>
            current.some((item) => item.id === level.id)
                ? current
                : [...current, level]
        )
        setGradeLevelsAttempt((attempt) => attempt + 1)
        return level
    }

    async function handleDeleteGradeLevel(level: GradeLevel): Promise<void> {
        await deleteGradeLevel(level.id)
        setGradeLevels((current) =>
            current.filter((item) => item.id !== level.id)
        )
    }

    if (session.isLoading) {
        return <PageLoader />
    }

    if (page === "login" && !currentUser) {
        return (
            <DashboardAuthentication
                challenge={session.challenge}
                title={t("professor-space")}
                notice={session.expired ? t("staff-session-expired") : null}
                onLogin={session.signIn}
                onVerify={session.completeTwoFactor}
                onCancelChallenge={session.cancelChallenge}
            />
        )
    }

    if (!currentUser || !activeEntry) return null

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
            {gradeLevelsFailed && (
                <div className="mt-6">
                    <LoadErrorNotice
                        message={t("grade-levels-load-error")}
                        onRetry={() =>
                            setGradeLevelsAttempt((attempt) => attempt + 1)
                        }
                    />
                </div>
            )}
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

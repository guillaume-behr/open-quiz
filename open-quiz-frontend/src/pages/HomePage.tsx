import {
    clearStudentSession,
    loginStudent,
    readStudentToken,
    restoreStudent,
} from "@/api/student-auth"
import { joinQuiz } from "@/api/quizzes"
import type { StudentAccount } from "@/api/types"
import { StudentLogin } from "@/components/forms/student-login"
import { JoinQuizForm } from "@/components/forms/join-quiz-form"
import {
    STUDENT_ACCESS_CARD_CLASS_NAME,
    StudentAccessHeader,
} from "@/components/forms/student-access-card"
import {
    DashboardShell,
    type DashboardEntry,
} from "@/components/navigation/dashboard-shell"
import {
    readStoredQuizSession,
    storeQuizSession,
} from "@/components/student-quiz/student-quiz-session"
import { Button } from "@/components/ui/button"
import { PageLoader } from "@/components/ui/page-loader"
import { ClipboardPenLine, Dumbbell, History, RotateCcw } from "lucide-react"
import { lazy, type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { localizedAuthErrorMessage } from "@/lib/errors"
import { useLocation, useNavigate } from "react-router"

type StudentRouteState = {
    student?: StudentAccount
    token?: string
    section?: StudentSection
}

const TrainingQuizzesPanel = lazy(() =>
    import("@/components/training/training-quizzes-panel").then((module) => ({
        default: module.TrainingQuizzesPanel,
    }))
)
const StudentQuizHistory = lazy(() =>
    import("@/components/student-quiz/student-quiz-history").then((module) => ({
        default: module.StudentQuizHistory,
    }))
)
const StudentMakeupPanel = lazy(() =>
    import("@/components/student-quiz/student-makeup-panel").then((module) => ({
        default: module.StudentMakeupPanel,
    }))
)

type StudentSection = "exam" | "training" | "makeup" | "results"

export function HomePage({
    page,
    initialSection = "exam",
}: {
    page: "login" | "dashboard"
    initialSection?: StudentSection
}) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const location = useLocation()
    const routeState = location.state as StudentRouteState | null
    const [student, setStudent] = useState<StudentAccount | null>(
        routeState?.student ?? null
    )
    const [token, setToken] = useState<string | null>(
        routeState?.token ?? readStudentToken()
    )
    const [identifier, setIdentifier] = useState("")
    const [password, setPassword] = useState("")
    const [isLoading, setIsLoading] = useState(Boolean(token && !student))
    const [isBusy, setIsBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [joinCode, setJoinCode] = useState("")
    const [joinError, setJoinError] = useState<string | null>(null)
    const [isJoining, setIsJoining] = useState(false)
    const [storedExam] = useState(readStoredQuizSession)
    const [activeTab, setActiveTab] = useState<StudentSection>(
        routeState?.section ?? initialSection
    )
    const dashboardEntries: DashboardEntry<StudentSection>[] = [
        {
            id: "exam",
            icon: ClipboardPenLine,
            label: t("exams-tab"),
            description: t("enter-exam-help"),
        },
        {
            id: "training",
            icon: Dumbbell,
            label: t("training-tab"),
            description: t("training-no-score-help"),
        },
        {
            id: "makeup",
            icon: RotateCcw,
            label: t("makeup-tab"),
            description: t("makeup-code-help"),
        },
        {
            id: "results",
            icon: History,
            label: t("results"),
            description: t("quiz-history-empty-help"),
        },
    ]
    const activeEntry =
        dashboardEntries.find((entry) => entry.id === activeTab) ??
        dashboardEntries[0]

    function selectSection(section: StudentSection) {
        setActiveTab(section)
        const destination =
            section === "results" ? "/student/results" : "/student/dashboard"
        if (location.pathname !== destination) {
            navigate(destination, {
                replace: true,
                state: { student, token, section },
            })
        }
    }

    useEffect(() => {
        if (!token) {
            if (page === "dashboard")
                navigate("/student/login", { replace: true })
            return
        }
        if (student) {
            if (page === "login")
                navigate("/student/dashboard", {
                    replace: true,
                    state: { student, token },
                })
            return
        }
        restoreStudent(token)
            .then((restored) => {
                setStudent(restored)
                if (page === "login")
                    navigate("/student/dashboard", {
                        replace: true,
                        state: { student: restored, token },
                    })
            })
            .catch(() => {
                clearStudentSession()
                setToken(null)
                if (page === "dashboard")
                    navigate("/student/login", { replace: true })
            })
            .finally(() => setIsLoading(false))
    }, [navigate, page, student, token])

    useEffect(() => {
        const previousTitle = document.title
        document.title = `Open Quiz | ${t("student-dashboard")}`
        return () => {
            document.title = previousTitle
        }
    }, [t])

    async function handleLogin(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setIsBusy(true)
        setError(null)
        try {
            const result = await loginStudent(identifier.trim(), password)
            setPassword("")
            navigate("/student/dashboard", {
                replace: true,
                state: { student: result.student, token: result.token },
            })
        } catch (caught) {
            setError(
                localizedAuthErrorMessage(caught, t, t("student-login-error"))
            )
        } finally {
            setIsBusy(false)
        }
    }

    function logout() {
        clearStudentSession()
        setStudent(null)
        setToken(null)
        navigate("/student/login", { replace: true })
    }

    async function joinExam(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!token) return
        setIsJoining(true)
        setJoinError(null)
        try {
            const joined = await joinQuiz(joinCode.trim(), token)
            storeQuizSession({
                joinCode: joined.join_code,
                participantToken: joined.participant_token,
            })
            navigate("/student/exam", { state: { student, token } })
        } catch {
            setJoinError(t("join-quiz-error"))
        } finally {
            setIsJoining(false)
        }
    }

    if (isLoading) {
        return <PageLoader />
    }

    if (page === "login" && (!student || !token)) {
        return (
            <div className="flex flex-1 items-center justify-center px-4">
                <StudentLogin
                    identifier={identifier}
                    password={password}
                    isBusy={isBusy}
                    error={error}
                    onIdentifierChange={setIdentifier}
                    onPasswordChange={setPassword}
                    onSubmit={handleLogin}
                />
            </div>
        )
    }

    if (!student || !token) return null

    return (
        <DashboardShell
            entries={dashboardEntries}
            activeEntry={activeEntry}
            welcome={t("student-dashboard-welcome", {
                name: student.display_name,
            })}
            help={t("student-dashboard-help")}
            menuLabel={t("dashboard-menu")}
            navigationLabel={t("student-activities")}
            signOutLabel={t("sign-out")}
            loadingLabel={t("page-loading")}
            onSelect={selectSection}
            onSignOut={logout}
            showActiveEntryIcon={activeTab !== "makeup"}
        >
            {activeTab === "exam" ? (
                <div className="mt-6 flex justify-center">
                    {storedExam ? (
                        <div className={STUDENT_ACCESS_CARD_CLASS_NAME}>
                            <StudentAccessHeader
                                title={t("resume-quiz")}
                                description={t("enter-exam-help")}
                                headingLevel={3}
                            />
                            <Button
                                className="h-12 w-full text-base"
                                onClick={() =>
                                    navigate("/student/exam", {
                                        state: { student, token },
                                    })
                                }
                            >
                                <ClipboardPenLine />
                                {t("resume-quiz")}
                            </Button>
                        </div>
                    ) : (
                        <JoinQuizForm
                            embedded
                            joinCode={joinCode}
                            isBusy={isJoining}
                            error={joinError}
                            onJoinCodeChange={(value) => {
                                setJoinCode(value)
                                setJoinError(null)
                            }}
                            onSubmit={joinExam}
                        />
                    )}
                </div>
            ) : activeTab === "training" ? (
                <div className="mt-6">
                    <TrainingQuizzesPanel student={student} token={token} />
                </div>
            ) : activeTab === "makeup" ? (
                <div className="mt-6 flex justify-center">
                    <StudentMakeupPanel token={token} />
                </div>
            ) : (
                <div className="mt-6">
                    <StudentQuizHistory token={token} />
                </div>
            )}
        </DashboardShell>
    )
}

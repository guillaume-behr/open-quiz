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
import { TrainingQuizzesPanel } from "@/components/training/training-quizzes-panel"
import { StudentQuizHistory } from "@/components/student-quiz/student-quiz-history"
import { StudentMakeupPanel } from "@/components/student-quiz/student-makeup-panel"
import {
    readStoredQuizSession,
    storeQuizSession,
} from "@/components/student-quiz/student-quiz-session"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"
import {
    ClipboardPenLine,
    Dumbbell,
    History,
    LoaderCircle,
    LogOut,
    RotateCcw,
    type LucideIcon,
} from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useLocation, useNavigate } from "react-router"

type StudentRouteState = {
    student?: StudentAccount
    token?: string
}

type StudentSection = "exam" | "training" | "makeup" | "history"

type StudentDashboardEntry = {
    id: StudentSection
    icon: LucideIcon
    label: string
    description: string
}

export function HomePage({ page }: { page: "login" | "dashboard" }) {
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
    const [activeTab, setActiveTab] = useState<StudentSection>("exam")
    const dashboardEntries: StudentDashboardEntry[] = [
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
            id: "history",
            icon: History,
            label: t("history-tab"),
            description: t("quiz-history-empty-help"),
        },
    ]
    const activeEntry =
        dashboardEntries.find((entry) => entry.id === activeTab) ??
        dashboardEntries[0]

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
        } catch {
            setError(t("student-login-error"))
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
        return (
            <div
                className="flex flex-1 items-center justify-center"
                role="status"
                aria-label={t("page-loading")}
            >
                <LoaderCircle className="size-9 animate-spin text-primary" />
            </div>
        )
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
        <div className="flex w-full flex-1 flex-col gap-4 overflow-y-auto px-4 py-2 sm:px-6 lg:px-10">
            <div className="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <h1 className="text-3xl font-extrabold">
                        {t("student-dashboard-welcome", {
                            name: student.display_name,
                        })}
                    </h1>
                    <p className="mt-1 text-sm text-muted-foreground">
                        {t("student-dashboard-help")}
                    </p>
                </div>
                <Button variant="outline" onClick={logout}>
                    <LogOut />
                    {t("sign-out")}
                </Button>
            </div>

            <div className="grid min-h-0 min-w-0 flex-1 gap-4 lg:grid-cols-[260px_minmax(0,1fr)]">
                <aside className="h-fit min-w-0 rounded-2xl border bg-card p-3 shadow-sm">
                    <p className="px-3 py-2 text-xs font-semibold tracking-wider text-muted-foreground uppercase">
                        {t("dashboard-menu")}
                    </p>
                    <nav
                        className="flex gap-2 overflow-x-auto lg:flex-col lg:overflow-visible"
                        aria-label={t("student-activities")}
                    >
                        {dashboardEntries.map((entry) => {
                            const Icon = entry.icon
                            const isActive = entry.id === activeTab
                            return (
                                <button
                                    key={entry.id}
                                    type="button"
                                    onClick={() => setActiveTab(entry.id)}
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
                    className="min-h-72 min-w-0 overflow-hidden rounded-2xl border bg-card p-4 shadow-sm sm:p-5"
                    aria-labelledby={`${activeEntry.id}-title`}
                >
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
                    {activeTab === "exam" ? (
                        <div className="mt-6">
                            {storedExam ? (
                                <div className="w-full max-w-md rounded-xl border bg-background p-5">
                                    <Button
                                        className="w-full"
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
                            <TrainingQuizzesPanel
                                student={student}
                                token={token}
                            />
                        </div>
                    ) : activeTab === "makeup" ? (
                        <div className="mt-6">
                            <StudentMakeupPanel token={token} />
                        </div>
                    ) : (
                        <div className="mt-6">
                            <StudentQuizHistory token={token} />
                        </div>
                    )}
                </section>
            </div>
        </div>
    )
}

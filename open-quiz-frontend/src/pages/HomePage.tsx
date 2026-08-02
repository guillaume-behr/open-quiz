import {
    clearStudentSession,
    loginStudent,
    readStudentToken,
    restoreStudent,
} from "@/api/student-auth"
import type { StudentAccount } from "@/api/types"
import { StudentLogin } from "@/components/forms/student-login"
import { TrainingQuizzesPanel } from "@/components/training/training-quizzes-panel"
import { Button } from "@/components/ui/button"
import {
    ClipboardPenLine,
    Dumbbell,
    GraduationCap,
    LoaderCircle,
    LogOut,
} from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useLocation, useNavigate } from "react-router"

type StudentRouteState = {
    student?: StudentAccount
    token?: string
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
    const [activeTab, setActiveTab] = useState<"exam" | "training">("exam")

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

    if (isLoading) {
        return (
            <div className="flex flex-1 items-center justify-center">
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
        <div className="flex flex-1 flex-col px-4">
            <div className="mx-auto flex w-full max-w-5xl items-center justify-between gap-3 py-2">
                <p className="text-sm text-muted-foreground">
                    {t("signed-in-as", { name: student.display_name })}
                </p>
                <Button variant="outline" size="sm" onClick={logout}>
                    <LogOut />
                    {t("sign-out")}
                </Button>
            </div>
            <div className="flex flex-1 items-center justify-center">
                <section className="w-full max-w-3xl rounded-2xl border bg-card p-6 shadow-lg sm:p-10">
                    <div className="flex flex-col items-center text-center">
                        <div className="rounded-2xl bg-primary/10 p-4 text-primary">
                            <GraduationCap className="size-10" />
                        </div>
                        <h1 className="mt-4 text-3xl font-extrabold">
                            {t("student-dashboard-welcome", {
                                name: student.display_name,
                            })}
                        </h1>
                        <p className="mt-2 max-w-xl text-muted-foreground">
                            {t("student-dashboard-help")}
                        </p>
                    </div>
                    <div
                        className="mt-8 flex rounded-xl bg-muted p-1"
                        role="tablist"
                        aria-label={t("student-activities")}
                    >
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "exam"}
                            className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition ${activeTab === "exam" ? "bg-background text-primary shadow-sm" : "text-muted-foreground"}`}
                            onClick={() => setActiveTab("exam")}
                        >
                            <ClipboardPenLine className="size-4" />
                            {t("exams-tab")}
                        </button>
                        <button
                            type="button"
                            role="tab"
                            aria-selected={activeTab === "training"}
                            className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition ${activeTab === "training" ? "bg-background text-primary shadow-sm" : "text-muted-foreground"}`}
                            onClick={() => setActiveTab("training")}
                        >
                            <Dumbbell className="size-4" />
                            {t("training-tab")}
                        </button>
                    </div>
                    {activeTab === "exam" ? (
                        <div className="mt-6 grid gap-4 sm:grid-cols-2">
                            <button
                                type="button"
                                className="group flex min-h-40 flex-col items-start justify-between rounded-2xl border bg-background p-5 text-left transition hover:border-primary hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none sm:col-span-2"
                                onClick={() =>
                                    navigate("/student/exam", {
                                        state: { student, token },
                                    })
                                }
                            >
                                <span className="rounded-xl bg-primary/10 p-3 text-primary transition group-hover:bg-primary group-hover:text-primary-foreground">
                                    <ClipboardPenLine className="size-7" />
                                </span>
                                <span>
                                    <span className="block text-xl font-bold">
                                        {t("enter-exam")}
                                    </span>
                                    <span className="mt-1 block text-sm text-muted-foreground">
                                        {t("enter-exam-help")}
                                    </span>
                                </span>
                            </button>
                        </div>
                    ) : (
                        <div className="mt-6">
                            <TrainingQuizzesPanel
                                student={student}
                                token={token}
                            />
                        </div>
                    )}
                </section>
            </div>
        </div>
    )
}

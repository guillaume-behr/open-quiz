import {
    clearStudentSession,
    readStudentToken,
    restoreStudent,
} from "@/api/student-auth"
import type { StudentAccount } from "@/api/types"
import { StudentQuiz } from "@/components/student-quiz/student-quiz"
import { readStoredQuizSession } from "@/components/student-quiz/student-quiz-session"
import { PageLoader } from "@/components/ui/page-loader"
import { useCallback, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useLocation, useNavigate } from "react-router"

type ExamLocationState = {
    student?: StudentAccount
    token?: string
}

export function ExamPage() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const location = useLocation()
    const routeState = location.state as ExamLocationState | null
    const [token] = useState(() => routeState?.token ?? readStudentToken())
    const [student, setStudent] = useState<StudentAccount | null>(
        routeState?.student ?? null
    )
    const [isLoading, setIsLoading] = useState(Boolean(token && !student))
    const returnToDashboard = useCallback(() => {
        navigate("/student/dashboard", { replace: true })
    }, [navigate])

    useEffect(() => {
        if (!readStoredQuizSession()) {
            navigate("/student/dashboard", { replace: true })
            return
        }
        if (!token) {
            navigate("/student/login", { replace: true })
            return
        }
        if (student) return
        restoreStudent(token)
            .then(setStudent)
            .catch(() => {
                clearStudentSession()
                navigate("/student/login", { replace: true })
            })
            .finally(() => setIsLoading(false))
    }, [navigate, student, token])

    useEffect(() => {
        const previousTitle = document.title
        document.title = `Open Quiz | ${t("exam-mode")}`
        return () => {
            document.title = previousTitle
        }
    }, [t])

    if (isLoading || !student || !token) {
        return <PageLoader />
    }

    return (
        <div className="flex flex-1 flex-col px-4 py-4 sm:px-6">
            <div className="flex flex-1 items-center justify-center">
                <StudentQuiz
                    studentToken={token}
                    onSessionCleared={returnToDashboard}
                />
            </div>
        </div>
    )
}

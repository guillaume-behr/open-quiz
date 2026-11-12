import { rememberedStudentFor } from "@/lib/student-session-storage"
import { usePageTitle } from "@/hooks/use-page-title"
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
import { useNavigate } from "react-router"

export function ExamPage() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [token] = useState(readStudentToken)
    const [student, setStudent] = useState<StudentAccount | null>(() =>
        rememberedStudentFor(token)
    )
    const [isLoading, setIsLoading] = useState(Boolean(token && !student))
    const returnToDashboard = useCallback(() => {
        void navigate("/student/dashboard", { replace: true })
    }, [navigate])

    useEffect(() => {
        if (!readStoredQuizSession()) {
            void navigate("/student/dashboard", { replace: true })
            return
        }
        if (!token) {
            void navigate("/student/login", { replace: true })
            return
        }
        if (student) return
        restoreStudent(token)
            .then(setStudent)
            .catch(() => {
                clearStudentSession()
                void navigate("/student/login", { replace: true })
            })
            .finally(() => setIsLoading(false))
    }, [navigate, student, token])

    usePageTitle(t("exam-mode"))

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

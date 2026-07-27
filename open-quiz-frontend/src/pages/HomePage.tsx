import { JoinQuizForm } from "@/components/forms/join-quiz-form"
import { restoreSession } from "@/api/api"
import { LoaderCircle } from "lucide-react"
import { useEffect, useState } from "react"
import { useNavigate } from "react-router"

export function HomePage() {
    const navigate = useNavigate()
    const [isCheckingSession, setIsCheckingSession] = useState(true)

    useEffect(() => {
        restoreSession()
            .then((user) => {
                navigate(
                    user.is_admin ? "/admin/dashboard" : "/dashboard",
                    { replace: true }
                )
            })
            .catch(() => setIsCheckingSession(false))
    }, [navigate])

    if (isCheckingSession) {
        return (
            <div className="flex flex-1 items-center justify-center">
                <LoaderCircle className="size-9 animate-spin text-primary" />
            </div>
        )
    }

    return (
        <div className="flex flex-1 items-center justify-center px-4">
            <JoinQuizForm />
        </div>
    )
}

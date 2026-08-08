import { getTrainingQuestionBanks, startTrainingQuiz } from "@/api/quizzes"
import type { QuestionBank, StudentAccount } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dumbbell, LoaderCircle, Play } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

export function TrainingQuizzesPanel({
    student,
    token,
}: {
    student: StudentAccount
    token: string
}) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [banks, setBanks] = useState<QuestionBank[]>([])
    const [isLoading, setIsLoading] = useState(true)
    const [startingId, setStartingId] = useState<number | null>(null)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        let active = true
        getTrainingQuestionBanks(token)
            .then((items) => {
                if (active) setBanks(items)
            })
            .catch(() => active && setError(t("training-load-error")))
            .finally(() => active && setIsLoading(false))
        return () => {
            active = false
        }
    }, [t, token])

    async function start(bank: QuestionBank) {
        setStartingId(bank.id)
        setError(null)
        try {
            const joined = await startTrainingQuiz(bank.id, token)
            const { participant_token: participantToken, ...session } = joined
            try {
                sessionStorage.setItem(
                    "open-quiz-training-session",
                    JSON.stringify({
                        joinCode: session.join_code,
                        participantToken,
                    })
                )
            } catch {
                // Route state keeps the current training usable without storage.
            }
            navigate("/student/training", {
                state: { student, token, session, participantToken },
            })
        } catch {
            setError(t("training-start-error"))
        } finally {
            setStartingId(null)
        }
    }

    if (isLoading) {
        return (
            <div
                className="flex min-h-48 items-center justify-center"
                role="status"
                aria-label={t("page-loading")}
            >
                <LoaderCircle className="size-8 animate-spin text-primary motion-reduce:animate-none" />
            </div>
        )
    }

    return (
        <div>
            {error && (
                <p className="mb-4 text-sm text-destructive" role="alert">
                    {error}
                </p>
            )}
            {banks.length === 0 ? (
                <div className="flex min-h-48 flex-col items-center justify-center rounded-xl border border-dashed text-center text-muted-foreground">
                    <Dumbbell className="mb-3 size-9" />
                    <p className="font-semibold">{t("no-training-quiz")}</p>
                    <p className="mt-1 text-sm">{t("no-training-quiz-help")}</p>
                </div>
            ) : (
                <div
                    key={banks.map((bank) => bank.id).join(",")}
                    className="grid animate-in gap-4 duration-300 fade-in-0 slide-in-from-bottom-2 motion-reduce:animate-none sm:grid-cols-2"
                >
                    {banks.map((bank) => (
                        <article
                            key={bank.id}
                            className="flex flex-col rounded-xl border bg-background p-5"
                        >
                            <Dumbbell className="size-7 text-primary" />
                            <h3 className="mt-4 text-lg font-bold">
                                {bank.chapter}
                            </h3>
                            <p className="mt-1 text-sm text-muted-foreground">
                                {bank.grade_level} ·{" "}
                                {t("training-quiz-summary", {
                                    count: bank.question_count,
                                })}
                            </p>
                            <p className="mt-3 text-xs text-muted-foreground">
                                {t("training-no-score-help")}
                            </p>
                            <Button
                                className="mt-5"
                                onClick={() => void start(bank)}
                                disabled={
                                    startingId !== null ||
                                    bank.question_count === 0
                                }
                            >
                                {startingId === bank.id ? (
                                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                                ) : (
                                    <Play />
                                )}
                                {t("start-training")}
                            </Button>
                        </article>
                    ))}
                </div>
            )}
        </div>
    )
}

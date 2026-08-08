import { getStudentQuizSession, submitStudentQuizAnswer } from "@/api/quizzes"
import type {
    StudentAccount,
    StudentQuizQuestion,
    StudentQuizSession,
    TrainingFeedback,
} from "@/api/types"
import { StudentQuestionForm } from "@/components/student-quiz/student-question-form"
import { Button } from "@/components/ui/button"
import { isRtlLanguage } from "@/lib/utils"
import { ArrowLeft, CheckCircle2, LoaderCircle, XCircle } from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"
import { useLocation, useNavigate } from "react-router"

type TrainingRouteState = {
    student?: StudentAccount
    token?: string
    session?: StudentQuizSession
    participantToken?: string
}

function storedTraining(): {
    joinCode: string
    participantToken: string
} | null {
    try {
        const value = JSON.parse(
            sessionStorage.getItem("open-quiz-training-session") ?? "null"
        ) as { joinCode?: unknown; participantToken?: unknown } | null
        return value &&
            typeof value.joinCode === "string" &&
            typeof value.participantToken === "string"
            ? {
                  joinCode: value.joinCode,
                  participantToken: value.participantToken,
              }
            : null
    } catch {
        return null
    }
}

export function TrainingPage() {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const location = useLocation()
    const routeState = location.state as TrainingRouteState | null
    const [stored] = useState(storedTraining)
    const [participantToken] = useState(
        routeState?.participantToken ?? stored?.participantToken ?? null
    )
    const [session, setSession] = useState<StudentQuizSession | null>(
        routeState?.session ?? null
    )
    const [selectedChoiceIds, setSelectedChoiceIds] = useState<number[]>([])
    const [writtenAnswer, setWrittenAnswer] = useState("")
    const [feedback, setFeedback] = useState<TrainingFeedback | null>(null)
    const [answeredQuestion, setAnsweredQuestion] =
        useState<StudentQuizQuestion | null>(null)
    const [nextSession, setNextSession] = useState<StudentQuizSession | null>(
        null
    )
    const [isBusy, setIsBusy] = useState(Boolean(!session && stored))
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (session || !stored || !participantToken) {
            if (!session && !stored)
                navigate("/student/dashboard", { replace: true })
            return
        }
        getStudentQuizSession(stored.joinCode, participantToken)
            .then(setSession)
            .catch(() => {
                clearStoredTraining()
                navigate("/student/dashboard", { replace: true })
            })
            .finally(() => setIsBusy(false))
    }, [navigate, participantToken, session, stored])

    async function submit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!session?.question || !participantToken) return
        setIsBusy(true)
        setError(null)
        try {
            const question = session.question
            const updated = await submitStudentQuizAnswer(
                session.join_code,
                participantToken,
                question.answer_mode === "written"
                    ? { written_answer: writtenAnswer }
                    : { selected_choice_ids: selectedChoiceIds }
            )
            if (!updated.training_feedback) throw new Error("Missing feedback")
            setAnsweredQuestion(question)
            setFeedback(updated.training_feedback)
            setNextSession(updated)
        } catch {
            setError(t("training-answer-error"))
        } finally {
            setIsBusy(false)
        }
    }

    function continueTraining() {
        if (!nextSession) return
        setSession(nextSession)
        setNextSession(null)
        setFeedback(null)
        setAnsweredQuestion(null)
        setSelectedChoiceIds([])
        setWrittenAnswer("")
        if (nextSession.status === "finished") clearStoredTraining()
    }

    if (!session || !participantToken) {
        return (
            <div className="flex flex-1 items-center justify-center">
                <LoaderCircle className="size-9 animate-spin text-primary" />
            </div>
        )
    }

    return (
        <div className="flex flex-1 flex-col px-4 py-2">
            <div className="mx-auto mb-4 flex w-full max-w-2xl justify-start">
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate("/student/dashboard")}
                >
                    <ArrowLeft />
                    {t("student-dashboard")}
                </Button>
            </div>
            <main className="mx-auto w-full max-w-2xl rounded-2xl border bg-secondary p-6 shadow-lg sm:p-10">
                <div className="mb-6 text-center">
                    <p className="text-sm font-semibold text-primary">
                        {t("training-mode")}
                    </p>
                    <h1 className="mt-1 text-3xl font-extrabold">
                        {session.quiz_title}
                    </h1>
                </div>
                {feedback && answeredQuestion ? (
                    <TrainingCorrection
                        question={answeredQuestion}
                        feedback={feedback}
                        onContinue={continueTraining}
                    />
                ) : session.status === "finished" ? (
                    <div className="rounded-xl bg-primary/10 p-8 text-center">
                        <CheckCircle2 className="mx-auto size-12 text-primary" />
                        <h2 className="mt-3 text-2xl font-bold">
                            {t("training-finished")}
                        </h2>
                        <p className="mt-2 text-muted-foreground">
                            {t("training-finished-help")}
                        </p>
                        <Button
                            className="mt-5"
                            onClick={() => navigate("/student/dashboard")}
                        >
                            {t("back-to-training-list")}
                        </Button>
                    </div>
                ) : session.question ? (
                    <StudentQuestionForm
                        session={session}
                        question={session.question}
                        participantToken={participantToken}
                        contentDirection={
                            isRtlLanguage(session.source_language)
                                ? "rtl"
                                : "ltr"
                        }
                        selectedChoiceIds={selectedChoiceIds}
                        writtenAnswer={writtenAnswer}
                        isBusy={isBusy}
                        error={error}
                        onSelectedChoiceIdsChange={setSelectedChoiceIds}
                        onWrittenAnswerChange={setWrittenAnswer}
                        onPrevious={() => undefined}
                        onSubmit={submit}
                    />
                ) : null}
            </main>
        </div>
    )
}

function TrainingCorrection({
    question,
    feedback,
    onContinue,
}: {
    question: StudentQuizQuestion
    feedback: TrainingFeedback
    onContinue: () => void
}) {
    const { t } = useTranslation()
    const correctLabels = question.choices
        .filter((choice) => feedback.correct_choice_ids.includes(choice.id))
        .map((choice) => choice.label)
    return (
        <section
            className={`rounded-xl border p-6 ${feedback.is_correct ? "border-emerald-500/50 bg-emerald-500/10" : "border-amber-500/50 bg-amber-500/10"}`}
        >
            <div className="flex items-center gap-3">
                {feedback.is_correct ? (
                    <CheckCircle2 className="size-7 text-emerald-700 dark:text-emerald-300" />
                ) : (
                    <XCircle className="size-7 text-amber-700 dark:text-amber-300" />
                )}
                <h2 className="text-xl font-bold">
                    {t(
                        feedback.is_correct
                            ? "training-correct"
                            : "training-incorrect"
                    )}
                </h2>
            </div>
            <p className="mt-4 font-medium">{question.prompt}</p>
            <div className="mt-4 rounded-lg bg-background/80 p-4">
                <p className="text-sm font-semibold">{t("correct-answer")}</p>
                <p className="mt-1">
                    {feedback.expected_answer ?? correctLabels.join(", ")}
                </p>
            </div>
            <Button className="mt-5 w-full" onClick={onContinue}>
                {t("continue-training")}
            </Button>
        </section>
    )
}

function clearStoredTraining() {
    try {
        sessionStorage.removeItem("open-quiz-training-session")
    } catch {
        /* State is also cleared in memory. */
    }
}

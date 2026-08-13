import { getStudentQuizSession, submitStudentQuizAnswer } from "@/api/quizzes"
import type {
    StudentAccount,
    StudentQuizQuestion,
    StudentQuizSession,
    TrainingFeedback,
} from "@/api/types"
import { StudentQuestionForm } from "@/components/student-quiz/student-question-form"
import { Button } from "@/components/ui/button"
import { PageLoader } from "@/components/ui/page-loader"
import { NavbarAction } from "@/components/navigation/navbar-action"
import { isRtlLanguage } from "@/lib/utils"
import { ArrowLeft, CheckCircle2, Info, Scale, XCircle } from "lucide-react"
import { type FormEvent, useEffect, useRef, useState } from "react"
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
    const questionFormRef = useRef<HTMLDivElement>(null)
    const [questionFormHeight, setQuestionFormHeight] = useState<number | null>(
        null
    )

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
        setQuestionFormHeight(
            questionFormRef.current?.getBoundingClientRect().height ?? null
        )
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
        setQuestionFormHeight(null)
        if (nextSession.status === "finished") clearStoredTraining()
    }

    if (!session || !participantToken) {
        return <PageLoader />
    }

    return (
        <div className="flex flex-1 flex-col px-4 py-4 sm:px-6">
            <NavbarAction>
                <Button
                    variant="outline"
                    size="sm"
                    onClick={() => navigate("/student/dashboard")}
                >
                    <ArrowLeft />
                    {t("student-dashboard")}
                </Button>
            </NavbarAction>
            <div className="mx-auto my-auto w-full max-w-7xl rounded-2xl border bg-secondary p-5 shadow-lg sm:p-8 lg:p-12">
                <div className="mb-6 text-center">
                    <p className="text-sm font-semibold text-primary">
                        {t("training-mode")}
                    </p>
                    <h1 className="text-3xl font-extrabold">
                        {session.quiz_title}
                    </h1>
                </div>
                {feedback && answeredQuestion ? (
                    <TrainingCorrection
                        question={answeredQuestion}
                        feedback={feedback}
                        questionFormHeight={questionFormHeight}
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
                        {session.potential_score !== null && (
                            <div className="mx-auto mt-5 flex w-fit items-center gap-2 rounded-lg border bg-background px-4 py-3">
                                <Scale className="size-5 text-primary" />
                                <span className="font-semibold">
                                    {t("training-potential-score", {
                                        score: session.potential_score,
                                        maximum:
                                            session.potential_maximum_score ??
                                            0,
                                    })}
                                </span>
                                <button
                                    type="button"
                                    className="rounded-full p-1 text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                                    aria-label={t(
                                        "training-potential-score-help"
                                    )}
                                    title={t("training-potential-score-help")}
                                >
                                    <Info className="size-4" />
                                </button>
                            </div>
                        )}
                        <Button
                            className="mx-auto mt-6"
                            size="lg"
                            onClick={() =>
                                navigate("/student/dashboard", {
                                    replace: true,
                                })
                            }
                        >
                            {t("back-home")}
                        </Button>
                    </div>
                ) : session.question ? (
                    <div ref={questionFormRef}>
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
                            onNavigate={() => undefined}
                            onSubmit={submit}
                        />
                    </div>
                ) : null}
            </div>
        </div>
    )
}

function TrainingCorrection({
    question,
    feedback,
    questionFormHeight,
    onContinue,
}: {
    question: StudentQuizQuestion
    feedback: TrainingFeedback
    questionFormHeight: number | null
    onContinue: () => void
}) {
    const { t } = useTranslation()
    const correctLabels = question.choices
        .filter((choice) => feedback.correct_choice_ids.includes(choice.id))
        .map((choice) => choice.label)
    return (
        <section
            className={`flex flex-col rounded-xl border p-6 ${feedback.requires_manual_review ? "border-border bg-muted/30" : feedback.is_correct ? "border-emerald-500/50 bg-emerald-500/10" : "border-destructive/50 bg-destructive/10"}`}
            style={
                questionFormHeight
                    ? { minHeight: `${questionFormHeight}px` }
                    : undefined
            }
        >
            <div className="flex items-center gap-3">
                {feedback.requires_manual_review ? (
                    <Scale className="size-7 text-muted-foreground" />
                ) : feedback.is_correct ? (
                    <CheckCircle2 className="size-7 text-emerald-700 dark:text-emerald-300" />
                ) : (
                    <XCircle className="size-7 text-destructive" />
                )}
                <h2 className="text-xl font-bold">
                    {t(
                        feedback.requires_manual_review
                            ? "training-manual-review"
                            : feedback.is_correct
                              ? "training-correct"
                              : "training-incorrect"
                    )}
                </h2>
            </div>
            <p className="mt-4 font-medium">{question.prompt}</p>
            {feedback.submitted_answer && (
                <div className="mt-4 rounded-lg bg-background/80 p-4">
                    <p className="text-sm font-semibold">
                        {t("student-answer")}
                    </p>
                    <p className="mt-1 whitespace-pre-wrap">
                        {feedback.submitted_answer}
                    </p>
                </div>
            )}
            <div className="mt-4 rounded-lg bg-background/80 p-4">
                <p className="text-sm font-semibold">{t("correct-answer")}</p>
                <p className="mt-1">
                    {feedback.expected_answer ?? correctLabels.join(", ")}
                </p>
            </div>
            <div className="mt-auto pt-5">
                <Button className="w-full" size="lg" onClick={onContinue}>
                    {t("continue-training")}
                </Button>
            </div>
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

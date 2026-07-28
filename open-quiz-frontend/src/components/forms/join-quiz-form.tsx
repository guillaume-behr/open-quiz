import {
    ApiError,
    getStudentQuizImage,
    getStudentQuizSession,
    joinQuiz,
    navigateStudentQuiz,
    reportStudentQuizViolation,
    submitStudentQuizAnswer,
    type StudentQuizSession,
} from "@/api/api"
import { Button } from "@/components/ui/button"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { QuizTimer } from "@/components/quizzes/quiz-timer"
import { LoaderCircle } from "lucide-react"
import { type FormEvent, useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"

const QUIZ_SESSION_STORAGE_KEY = "open-quiz-student-session"

type StoredQuizSession = {
    joinCode: string
    studentIdentifier: string
    participantToken: string
}

function readStoredQuizSession(): StoredQuizSession | null {
    try {
        const value = JSON.parse(
            sessionStorage.getItem(QUIZ_SESSION_STORAGE_KEY) ?? "null"
        ) as Partial<StoredQuizSession> | null
        return value &&
            typeof value.joinCode === "string" &&
            typeof value.studentIdentifier === "string" &&
            typeof value.participantToken === "string"
            ? {
                  joinCode: value.joinCode,
                  studentIdentifier: value.studentIdentifier,
                  participantToken: value.participantToken,
              }
            : null
    } catch {
        sessionStorage.removeItem(QUIZ_SESSION_STORAGE_KEY)
        return null
    }
}

function ProtectedQuizImage({
    path,
    id,
    joinCode,
    token,
    alt,
}: {
    path: "questions" | "choices"
    id: number
    joinCode: string
    token: string
    alt: string
}) {
    const [source, setSource] = useState<string | null>(null)

    useEffect(() => {
        let active = true
        let objectUrl: string | null = null
        void getStudentQuizImage(path, id, joinCode, token)
            .then((blob) => {
                objectUrl = URL.createObjectURL(blob)
                if (active) {
                    setSource(objectUrl)
                } else {
                    URL.revokeObjectURL(objectUrl)
                }
            })
            .catch(() => undefined)
        return () => {
            active = false
            if (objectUrl) URL.revokeObjectURL(objectUrl)
        }
    }, [id, joinCode, path, token])

    return source ? (
        <img
            className="max-h-80 rounded-lg object-contain"
            src={source}
            alt={alt}
        />
    ) : null
}

export function JoinQuizForm() {
    const { t } = useTranslation()
    const [restoredSession] = useState(readStoredQuizSession)
    const [studentIdentifier, setStudentIdentifier] = useState(
        restoredSession?.studentIdentifier ?? ""
    )
    const [joinCode, setJoinCode] = useState(restoredSession?.joinCode ?? "")
    const [participantToken, setParticipantToken] = useState<string | null>(
        restoredSession?.participantToken ?? null
    )
    const [session, setSession] = useState<StudentQuizSession | null>(null)
    const [selectedChoiceIds, setSelectedChoiceIds] = useState<number[]>([])
    const [writtenAnswer, setWrittenAnswer] = useState("")
    const [isBusy, setIsBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [isFullscreen, setIsFullscreen] = useState(
        Boolean(document.fullscreenElement)
    )
    const violationTimes = useRef<Record<string, number>>({})
    const monitoredJoinCode = session?.join_code

    useEffect(() => {
        if (!restoredSession) return
        let active = true
        void getStudentQuizSession(
            restoredSession.joinCode,
            restoredSession.participantToken
        )
            .then((restoredState) => {
                if (!active) return
                setSession(restoredState)
                setSelectedChoiceIds(
                    restoredState.selected_choice_ids ?? []
                )
                setWrittenAnswer(restoredState.written_answer ?? "")
            })
            .catch((restoreError: unknown) => {
                if (!active) return
                if (
                    restoreError instanceof ApiError &&
                    [401, 403, 404].includes(restoreError.status)
                ) {
                    sessionStorage.removeItem(QUIZ_SESSION_STORAGE_KEY)
                    setParticipantToken(null)
                }
                setError(t("student-session-restore-error"))
            })
        return () => {
            active = false
        }
    }, [restoredSession, t])

    useEffect(() => {
        if (!monitoredJoinCode || !participantToken) return
        const report = (
            eventType:
                | "fullscreen_exit"
                | "pointer_exit"
                | "window_blur"
                | "page_hidden"
        ) => {
            const now = Date.now()
            if (now - (violationTimes.current[eventType] ?? 0) < 1000) return
            violationTimes.current[eventType] = now
            void reportStudentQuizViolation(
                monitoredJoinCode,
                participantToken,
                eventType
            )
        }
        const fullscreenChanged = () => {
            const active = Boolean(document.fullscreenElement)
            setIsFullscreen(active)
            if (!active) report("fullscreen_exit")
        }
        const pointerLeft = (event: MouseEvent) => {
            if (event.relatedTarget === null) report("pointer_exit")
        }
        const blurred = () => report("window_blur")
        const visibilityChanged = () => {
            if (document.hidden) report("page_hidden")
        }
        document.addEventListener("fullscreenchange", fullscreenChanged)
        document.documentElement.addEventListener("mouseout", pointerLeft)
        window.addEventListener("blur", blurred)
        document.addEventListener("visibilitychange", visibilityChanged)
        if (!document.fullscreenElement) report("fullscreen_exit")
        return () => {
            document.removeEventListener("fullscreenchange", fullscreenChanged)
            document.documentElement.removeEventListener(
                "mouseout",
                pointerLeft
            )
            window.removeEventListener("blur", blurred)
            document.removeEventListener("visibilitychange", visibilityChanged)
        }
    }, [monitoredJoinCode, participantToken])

    useEffect(() => {
        if (!session || !participantToken || session.status === "finished")
            return
        let active = true
        const refresh = () => {
            void getStudentQuizSession(session.join_code, participantToken)
                .then((updated) => {
                    if (!active) return
                    if (updated.question?.id !== session.question?.id) {
                        setSelectedChoiceIds(updated.selected_choice_ids ?? [])
                        setWrittenAnswer(updated.written_answer ?? "")
                    }
                    setSession(updated)
                })
                .catch(() => {
                    if (active) setError(t("student-session-error"))
                })
        }
        const interval = window.setInterval(refresh, 1500)
        return () => {
            active = false
            window.clearInterval(interval)
        }
    }, [participantToken, session, t])

    async function handleJoin(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        void document.documentElement
            .requestFullscreen()
            .then(() => setIsFullscreen(true))
            .catch(() => setIsFullscreen(false))
        setError(null)
        setIsBusy(true)
        try {
            const joined = await joinQuiz(
                joinCode.trim(),
                studentIdentifier.trim()
            )
            const { participant_token, ...state } = joined
            sessionStorage.setItem(
                QUIZ_SESSION_STORAGE_KEY,
                JSON.stringify({
                    joinCode: state.join_code,
                    studentIdentifier: studentIdentifier.trim(),
                    participantToken: participant_token,
                } satisfies StoredQuizSession)
            )
            setParticipantToken(participant_token)
            setSession(state)
            setSelectedChoiceIds(state.selected_choice_ids ?? [])
            setWrittenAnswer(state.written_answer ?? "")
        } catch {
            setError(t("join-quiz-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function goToPreviousQuestion() {
        if (
            !session ||
            !participantToken ||
            !session.question_number ||
            session.question_number <= 1
        )
            return
        setIsBusy(true)
        try {
            const updated = await navigateStudentQuiz(
                session.join_code,
                participantToken,
                session.question_number - 1
            )
            setSession(updated)
            setSelectedChoiceIds(updated.selected_choice_ids ?? [])
            setWrittenAnswer(updated.written_answer ?? "")
        } catch {
            setError(t("student-navigation-error"))
        } finally {
            setIsBusy(false)
        }
    }

    async function handleAnswer(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        if (!session?.question || !participantToken) return
        setError(null)
        setIsBusy(true)
        try {
            const updated = await submitStudentQuizAnswer(
                session.join_code,
                participantToken,
                {
                    selected_choice_ids:
                        session.question.answer_mode === "written"
                            ? undefined
                            : selectedChoiceIds,
                    written_answer:
                        session.question.answer_mode === "written"
                            ? writtenAnswer
                            : undefined,
                }
            )
            setSelectedChoiceIds([])
            setWrittenAnswer("")
            setSession(updated)
        } catch {
            setError(t("student-answer-error"))
        } finally {
            setIsBusy(false)
        }
    }

    if (session) {
        if (!isFullscreen && session.status !== "finished") {
            return (
                <div className="flex w-full max-w-lg flex-col gap-5 rounded-2xl border bg-secondary px-8 py-10 text-center shadow-lg">
                    <p className="text-2xl font-bold">
                        {t("fullscreen-required")}
                    </p>
                    <p className="text-muted-foreground">
                        {t("fullscreen-required-help")}
                    </p>
                    <Button
                        size="lg"
                        onClick={() =>
                            void document.documentElement
                                .requestFullscreen()
                                .then(() => setIsFullscreen(true))
                        }
                    >
                        {t("enter-fullscreen")}
                    </Button>
                </div>
            )
        }
        const question = session.question
        return (
            <div className="flex w-full max-w-2xl flex-col gap-5 rounded-2xl border bg-secondary px-6 py-8 shadow-lg sm:px-10">
                <div className="text-center">
                    <p className="text-3xl font-extrabold">
                        {session.quiz_title}
                    </p>
                    <p className="text-muted-foreground">
                        {session.class_name}
                    </p>
                    {session.status === "in_progress" && (
                        <div className="mt-3">
                            <QuizTimer endsAt={session.ends_at} />
                        </div>
                    )}
                </div>
                {session.status === "waiting" && (
                    <div className="text-center">
                        <LoaderCircle className="mx-auto size-10 animate-spin text-primary" />
                        <p className="mt-3 font-semibold">
                            {t("student-waiting-for-start")}
                        </p>
                    </div>
                )}
                {session.status === "finished" && (
                    <div className="rounded-xl bg-primary/10 p-8 text-center">
                        <p className="text-2xl font-bold">
                            {t("student-quiz-finished")}
                        </p>
                    </div>
                )}
                {session.status === "in_progress" &&
                    session.has_answered &&
                    !session.question && (
                        <div className="rounded-xl border border-dashed p-8 text-center">
                            <LoaderCircle className="mx-auto size-8 animate-spin text-primary" />
                            <p className="mt-3 font-semibold">
                                {t("student-answer-recorded")}
                            </p>
                            <p className="text-sm text-muted-foreground">
                                {t("student-waiting-next")}
                            </p>
                        </div>
                    )}
                {session.status === "in_progress" && question && (
                    <form className="space-y-5" onSubmit={handleAnswer}>
                        <p className="text-sm font-semibold text-primary">
                            {t("student-question-progress", {
                                current: session.question_number,
                                total: session.total_questions,
                            })}
                        </p>
                        <div className="h-2 overflow-hidden rounded-full bg-muted">
                            <div
                                className="h-full rounded-full bg-primary transition-all"
                                style={{
                                    width: `${Math.round(
                                        (session.answered_count /
                                            session.total_questions) *
                                            100
                                    )}%`,
                                }}
                            />
                        </div>
                        <p className="text-xs text-muted-foreground">
                            {t("student-answered-progress", {
                                count: session.answered_count,
                                total: session.total_questions,
                            })}
                        </p>
                        <h2 className="text-xl font-bold">{question.prompt}</h2>
                        {question.has_image && participantToken && (
                            <ProtectedQuizImage
                                path="questions"
                                id={question.id}
                                joinCode={session.join_code}
                                token={participantToken}
                                alt={question.prompt}
                            />
                        )}
                        {question.code_content && (
                            <pre className="overflow-x-auto rounded-lg bg-slate-950 p-4 text-sm text-slate-50">
                                <code>{question.code_content}</code>
                            </pre>
                        )}
                        {question.answer_mode === "written" ? (
                            <textarea
                                className="min-h-32 w-full rounded-md border bg-background p-3"
                                value={writtenAnswer}
                                onChange={(event) =>
                                    setWrittenAnswer(event.target.value)
                                }
                                required
                            />
                        ) : (
                            <div className="grid gap-3">
                                {question.choices.map((choice) => {
                                    const checked = selectedChoiceIds.includes(
                                        choice.id
                                    )
                                    return (
                                        <label
                                            key={choice.id}
                                            className="flex cursor-pointer gap-3 rounded-xl border bg-background p-4"
                                        >
                                            <input
                                                type={
                                                    question.answer_mode ===
                                                    "single"
                                                        ? "radio"
                                                        : "checkbox"
                                                }
                                                name="answer"
                                                checked={checked}
                                                onChange={() =>
                                                    setSelectedChoiceIds(
                                                        (current) =>
                                                            question.answer_mode ===
                                                            "single"
                                                                ? [choice.id]
                                                                : checked
                                                                  ? current.filter(
                                                                        (id) =>
                                                                            id !==
                                                                            choice.id
                                                                    )
                                                                  : [
                                                                        ...current,
                                                                        choice.id,
                                                                    ]
                                                    )
                                                }
                                            />
                                            <span>
                                                {choice.label}
                                                {choice.has_image &&
                                                    participantToken && (
                                                        <ProtectedQuizImage
                                                            path="choices"
                                                            id={choice.id}
                                                            joinCode={
                                                                session.join_code
                                                            }
                                                            token={
                                                                participantToken
                                                            }
                                                            alt={choice.label}
                                                        />
                                                    )}
                                                {choice.code_content && (
                                                    <pre className="mt-2 overflow-x-auto rounded bg-slate-950 p-3 text-sm text-slate-50">
                                                        <code>
                                                            {
                                                                choice.code_content
                                                            }
                                                        </code>
                                                    </pre>
                                                )}
                                            </span>
                                        </label>
                                    )
                                })}
                            </div>
                        )}
                        {error && <FieldError>{error}</FieldError>}
                        <div className="flex gap-3">
                            {session.allow_previous_questions &&
                                (session.question_number ?? 1) > 1 && (
                                    <Button
                                        type="button"
                                        variant="outline"
                                        disabled={isBusy}
                                        onClick={() =>
                                            void goToPreviousQuestion()
                                        }
                                    >
                                        {t("previous-question")}
                                    </Button>
                                )}
                            <Button
                                className="flex-1"
                                size="lg"
                                disabled={
                                    isBusy ||
                                    (question.answer_mode !== "written" &&
                                        selectedChoiceIds.length === 0)
                                }
                            >
                                {isBusy && (
                                    <LoaderCircle className="animate-spin" />
                                )}
                                {t("student-submit-answer")}
                            </Button>
                        </div>
                    </form>
                )}
            </div>
        )
    }

    return (
        <form
            className="flex w-full max-w-md flex-col gap-5 rounded-2xl border bg-secondary px-6 py-10 shadow-lg sm:px-10 sm:py-15"
            onSubmit={handleJoin}
        >
            <div className="flex flex-col gap-2">
                <p className="text-center text-4xl font-extrabold">
                    {t("join-quiz-title")}
                </p>
                <p className="text-center font-light">
                    {t("join-quiz-instructions")}
                </p>
            </div>
            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="student-id">
                        {t("student-id")}
                    </FieldLabel>
                    <Input
                        className="py-6"
                        id="student-id"
                        name="student-id"
                        autoComplete="username"
                        spellCheck={false}
                        value={studentIdentifier}
                        onChange={(event) =>
                            setStudentIdentifier(event.target.value)
                        }
                        required
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="quiz-id">{t("quiz-id")}</FieldLabel>
                    <Input
                        className="py-6"
                        id="quiz-id"
                        name="quiz-id"
                        autoComplete="off"
                        spellCheck={false}
                        value={joinCode}
                        onChange={(event) =>
                            setJoinCode(event.target.value.toUpperCase())
                        }
                        required
                    />
                </Field>
                {error && (
                    <p className="text-sm text-destructive" role="alert">
                        {error}
                    </p>
                )}
                <Button
                    className="text-md py-7 shadow"
                    type="submit"
                    disabled={isBusy}
                >
                    {isBusy && <LoaderCircle className="animate-spin" />}
                    {t(isBusy ? "joining-quiz" : "join-quiz-button")}
                </Button>
            </FieldGroup>
        </form>
    )
}

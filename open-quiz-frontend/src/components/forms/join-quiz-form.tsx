import {
    getPublicQuizSession,
    joinQuiz,
    type StudentQuizSession,
} from "@/api/api"
import { LoaderCircle } from "lucide-react"
import { type FormEvent, useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"

export function JoinQuizForm() {
    const { t } = useTranslation()
    const [studentIdentifier, setStudentIdentifier] = useState("")
    const [joinCode, setJoinCode] = useState("")
    const [session, setSession] = useState<StudentQuizSession | null>(null)
    const [isJoining, setIsJoining] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const activeJoinCode = session?.join_code
    const sessionStatus = session?.status

    useEffect(() => {
        if (!activeJoinCode || sessionStatus !== "waiting") return
        let isActive = true
        const interval = window.setInterval(() => {
            void getPublicQuizSession(activeJoinCode)
                .then((updated) => {
                    if (isActive) setSession(updated)
                })
                .catch(() => undefined)
        }, 1500)
        return () => {
            isActive = false
            window.clearInterval(interval)
        }
    }, [activeJoinCode, sessionStatus])

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setError(null)
        setIsJoining(true)
        try {
            setSession(await joinQuiz(joinCode.trim(), studentIdentifier.trim()))
        } catch {
            setError(t("join-quiz-error"))
        } finally {
            setIsJoining(false)
        }
    }

    if (session) {
        return (
            <div className="flex w-full max-w-lg flex-col gap-5 rounded-2xl border bg-secondary px-10 py-12 text-center shadow-lg">
                <p className="text-3xl font-extrabold">{session.quiz_title}</p>
                <p className="text-muted-foreground">{session.class_name}</p>
                {session.status === "waiting" ? (
                    <>
                        <LoaderCircle className="mx-auto size-10 animate-spin text-primary" />
                        <p className="font-semibold">
                            {t("student-waiting-for-start")}
                        </p>
                    </>
                ) : (
                    <>
                        <div className="mx-auto flex size-14 items-center justify-center rounded-full bg-primary text-2xl text-primary-foreground">
                            ✓
                        </div>
                        <p className="text-xl font-bold">{t("quiz-started")}</p>
                    </>
                )}
            </div>
        )
    }

    return (
        <form
            className="flex w-full max-w-fit min-w-sm flex-col gap-5 rounded-2xl border bg-secondary px-10 py-15 shadow-lg"
            onSubmit={handleSubmit}
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
                        name="studentId"
                        value={studentIdentifier}
                        onChange={(event) =>
                            setStudentIdentifier(event.target.value)
                        }
                        autoComplete="username"
                        placeholder="Ex : marting5"
                        spellCheck={false}
                        required
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="quiz-id">{t("quiz-id")}</FieldLabel>
                    <Input
                        className="py-6"
                        id="quiz-id"
                        name="quizId"
                        value={joinCode}
                        onChange={(event) =>
                            setJoinCode(event.target.value.toUpperCase())
                        }
                        autoComplete="off"
                        placeholder="Ex : X45D9"
                        spellCheck={false}
                        required
                    />
                </Field>
                {error && <FieldError>{error}</FieldError>}

                <Button
                    className="text-md py-7 shadow"
                    type="submit"
                    disabled={isJoining}
                >
                    {isJoining && <LoaderCircle className="animate-spin" />}
                    {t(isJoining ? "joining-quiz" : "join-quiz-button")}
                </Button>
            </FieldGroup>
        </form>
    )
}

import { joinMakeupSession, selectMakeupQuiz } from "@/api/quizzes"
import type { MakeupJoin } from "@/api/types"
import { Button } from "@/components/ui/button"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { LoaderCircle, RotateCcw } from "lucide-react"
import {
    STUDENT_ACCESS_CARD_CLASS_NAME,
    StudentAccessHeader,
} from "@/components/forms/student-access-card"
import { storeQuizSession } from "./student-quiz-session"
import { useState, type FormEvent } from "react"
import { useTranslation } from "react-i18next"
import { useNavigate } from "react-router"

export function StudentMakeupPanel({ token }: { token: string }) {
    const { t } = useTranslation()
    const navigate = useNavigate()
    const [code, setCode] = useState("")
    const [lobby, setLobby] = useState<MakeupJoin | null>(null)
    const [busy, setBusy] = useState(false)
    const [error, setError] = useState<string | null>(null)

    async function join(event: FormEvent) {
        event.preventDefault()
        setBusy(true)
        setError(null)
        try {
            setLobby(await joinMakeupSession(code.trim().toUpperCase(), token))
        } catch {
            setError(t("makeup-join-error"))
        } finally {
            setBusy(false)
        }
    }

    async function select(quizId: number) {
        if (!lobby) return
        setBusy(true)
        setError(null)
        try {
            const joined = await selectMakeupQuiz(
                lobby.join_code,
                quizId,
                token
            )
            storeQuizSession({
                joinCode: joined.join_code,
                participantToken: joined.participant_token,
            })
            navigate("/student/exam")
        } catch {
            setError(t("makeup-select-error"))
        } finally {
            setBusy(false)
        }
    }

    if (lobby)
        return (
            <div className={STUDENT_ACCESS_CARD_CLASS_NAME}>
                <StudentAccessHeader
                    icon={RotateCcw}
                    title={t("makeup-tab")}
                    description={t("makeup-choose-help", {
                        className: lobby.class_name,
                    })}
                    headingLevel={3}
                />
                <div className="grid gap-3">
                    {lobby.quizzes.length ? (
                        lobby.quizzes.map((quiz) => (
                            <button
                                key={quiz.id}
                                type="button"
                                disabled={busy}
                                onClick={() => void select(quiz.id)}
                                className="flex items-center justify-between gap-4 rounded-xl border bg-card p-4 text-left transition hover:border-primary hover:shadow-sm focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                <span className="font-semibold break-words">
                                    {quiz.title}
                                </span>
                                <span className="shrink-0 text-sm text-muted-foreground">
                                    {Math.round(quiz.duration_seconds / 60)} min
                                </span>
                            </button>
                        ))
                    ) : (
                        <p className="rounded-xl border border-dashed p-4 text-center text-sm text-muted-foreground">
                            {t("makeup-no-eligible-quiz")}
                        </p>
                    )}
                    {error && <FieldError>{error}</FieldError>}
                    <Button
                        type="button"
                        variant="outline"
                        disabled={busy}
                        onClick={() => {
                            setLobby(null)
                            setError(null)
                        }}
                    >
                        {t("cancel")}
                    </Button>
                </div>
            </div>
        )

    return (
        <form onSubmit={join} className={STUDENT_ACCESS_CARD_CLASS_NAME}>
            <StudentAccessHeader
                icon={RotateCcw}
                title={t("makeup-tab")}
                description={t("makeup-code-help")}
                headingLevel={3}
            />
            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="makeup-session-code">
                        {t("join-code")}
                    </FieldLabel>
                    <Input
                        className="h-12 text-center font-mono text-lg font-semibold tracking-[0.25em] uppercase"
                        id="makeup-session-code"
                        name="makeup-session-code"
                        value={code}
                        onChange={(event) =>
                            setCode(event.target.value.toUpperCase())
                        }
                        minLength={4}
                        maxLength={8}
                        autoComplete="off"
                        spellCheck={false}
                        aria-invalid={Boolean(error)}
                        aria-describedby={
                            error ? "makeup-join-error" : undefined
                        }
                        required
                    />
                </Field>
                {error && (
                    <FieldError id="makeup-join-error">{error}</FieldError>
                )}
                <Button
                    className="h-12 text-base"
                    type="submit"
                    disabled={busy}
                >
                    {busy && (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    )}
                    {t(busy ? "joining-quiz" : "join-quiz-button")}
                </Button>
            </FieldGroup>
        </form>
    )
}

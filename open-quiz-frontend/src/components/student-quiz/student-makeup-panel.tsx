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
import { LoaderCircle } from "lucide-react"
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
            <div className="grid w-full max-w-md gap-3">
                <p className="text-sm text-muted-foreground">
                    {t("makeup-choose-help", { className: lobby.class_name })}
                </p>
                {lobby.quizzes.length ? (
                    lobby.quizzes.map((quiz) => (
                        <button
                            key={quiz.id}
                            type="button"
                            disabled={busy}
                            onClick={() => void select(quiz.id)}
                            className="flex items-center justify-between rounded-xl border bg-background p-4 text-left transition hover:border-primary hover:shadow-sm focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:cursor-not-allowed disabled:opacity-50"
                        >
                            <span className="font-semibold">{quiz.title}</span>
                            <span className="text-sm text-muted-foreground">
                                {Math.round(quiz.duration_seconds / 60)} min
                            </span>
                        </button>
                    ))
                ) : (
                    <p className="rounded-xl border p-4 text-sm text-muted-foreground">
                        {t("makeup-no-eligible-quiz")}
                    </p>
                )}
                {error && (
                    <p className="text-sm text-destructive" role="alert">
                        {error}
                    </p>
                )}
            </div>
        )

    return (
        <form
            onSubmit={join}
            className="flex w-full max-w-md flex-col gap-5 rounded-2xl border bg-secondary px-6 py-10 shadow-lg sm:px-10 sm:py-14"
        >
            <h3 className="text-center text-xl font-bold">
                {t("join-quiz-title")}
            </h3>
            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="makeup-session-code">
                        {t("join-code")}
                    </FieldLabel>
                    <Input
                        className="py-6 font-mono tracking-[0.2em] uppercase"
                        id="makeup-session-code"
                        value={code}
                        onChange={(event) =>
                            setCode(event.target.value.toUpperCase())
                        }
                        maxLength={8}
                        autoComplete="off"
                        spellCheck={false}
                        aria-invalid={Boolean(error)}
                        required
                    />
                </Field>
                {error && <FieldError>{error}</FieldError>}
                <Button
                    className="py-7 text-base"
                    type="submit"
                    disabled={busy}
                >
                    {busy && (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    )}
                    {t("join-quiz")}
                </Button>
            </FieldGroup>
        </form>
    )
}

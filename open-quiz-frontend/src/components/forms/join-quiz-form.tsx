import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { LoaderCircle } from "lucide-react"
import type { FormEvent } from "react"
import { useTranslation } from "react-i18next"

type JoinQuizFormProps = {
    joinCode: string
    isBusy: boolean
    error: string | null
    onJoinCodeChange: (value: string) => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function JoinQuizForm({
    joinCode,
    isBusy,
    error,
    onJoinCodeChange,
    onSubmit,
}: JoinQuizFormProps) {
    const { t } = useTranslation()

    return (
        <form
            className="flex w-full max-w-md flex-col gap-5 rounded-2xl border bg-secondary px-6 py-10 shadow-lg sm:px-10 sm:py-15"
            onSubmit={onSubmit}
        >
            <div className="flex flex-col gap-2">
                <h1 className="text-center text-4xl font-extrabold">
                    {t("join-quiz-title")}
                </h1>
                <p className="text-center font-light">
                    {t("join-quiz-instructions")}
                </p>
            </div>
            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="quiz-id">{t("quiz-id")}</FieldLabel>
                    <Input
                        className="py-6 font-mono tracking-[0.2em] uppercase"
                        id="quiz-id"
                        name="quiz-id"
                        autoComplete="off"
                        spellCheck={false}
                        value={joinCode}
                        minLength={4}
                        maxLength={8}
                        onChange={(event) =>
                            onJoinCodeChange(event.target.value.toUpperCase())
                        }
                        aria-invalid={Boolean(error)}
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

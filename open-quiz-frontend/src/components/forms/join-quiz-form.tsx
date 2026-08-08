import { Button } from "@/components/ui/button"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
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
    embedded?: boolean
}

export function JoinQuizForm({
    joinCode,
    isBusy,
    error,
    onJoinCodeChange,
    onSubmit,
    embedded = false,
}: JoinQuizFormProps) {
    const { t } = useTranslation()

    return (
        <form
            className="flex w-full max-w-md flex-col gap-5 rounded-2xl border bg-secondary px-6 py-10 shadow-lg sm:px-10 sm:py-14"
            onSubmit={onSubmit}
        >
            <div className="flex flex-col items-center gap-2 text-center">
                {embedded ? (
                    <h3 className="text-xl font-bold">
                        {t("join-quiz-title")}
                    </h3>
                ) : (
                    <h1 className="text-4xl font-extrabold">
                        {t("join-quiz-title")}
                    </h1>
                )}
                {!embedded && (
                    <p className="text-center font-light">
                        {t("join-quiz-instructions")}
                    </p>
                )}
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
                {error && <FieldError>{error}</FieldError>}
                <Button
                    className="py-7 text-base"
                    type="submit"
                    disabled={isBusy}
                >
                    {isBusy && (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    )}
                    {t(isBusy ? "joining-quiz" : "join-quiz-button")}
                </Button>
            </FieldGroup>
        </form>
    )
}

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
import {
    STUDENT_ACCESS_CARD_CLASS_NAME,
    StudentAccessHeader,
} from "./student-access-card"

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
        <form className={STUDENT_ACCESS_CARD_CLASS_NAME} onSubmit={onSubmit}>
            <StudentAccessHeader
                title={t("join-quiz-title")}
                description={t("join-quiz-instructions")}
                headingLevel={embedded ? 3 : 1}
            />
            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="quiz-id">{t("quiz-id")}</FieldLabel>
                    <Input
                        className="h-12 text-center font-mono text-lg font-semibold tracking-[0.25em] uppercase"
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
                        aria-describedby={error ? "join-quiz-error" : undefined}
                        required
                    />
                </Field>
                {error && <FieldError id="join-quiz-error">{error}</FieldError>}
                <Button
                    className="h-12 text-base"
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

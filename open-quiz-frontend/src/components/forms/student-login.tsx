import { Button } from "@/components/ui/button"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"
import { LoaderCircle, UserRound } from "lucide-react"
import type { FormEvent } from "react"
import { useTranslation } from "react-i18next"
import {
    STUDENT_ACCESS_CARD_CLASS_NAME,
    StudentAccessHeader,
} from "./student-access-card"

export function StudentLogin({
    identifier,
    password,
    isBusy,
    error,
    onIdentifierChange,
    onPasswordChange,
    onSubmit,
}: {
    identifier: string
    password: string
    isBusy: boolean
    error: string | null
    onIdentifierChange: (value: string) => void
    onPasswordChange: (value: string) => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}) {
    const { t } = useTranslation()
    return (
        <form className={STUDENT_ACCESS_CARD_CLASS_NAME} onSubmit={onSubmit}>
            <StudentAccessHeader
                icon={UserRound}
                title={t("student-login-title")}
                description={t("student-login-instructions")}
            />
            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="student-login-id">
                        {t("student-id")}
                    </FieldLabel>
                    <Input
                        id="student-login-id"
                        className="py-6"
                        autoComplete="username"
                        value={identifier}
                        onChange={(event) =>
                            onIdentifierChange(event.target.value)
                        }
                        required
                        aria-invalid={Boolean(error)}
                        aria-describedby={
                            error ? "student-login-error" : undefined
                        }
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="student-login-password">
                        {t("login-password")}
                    </FieldLabel>
                    <PasswordInput
                        id="student-login-password"
                        className="py-6"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) =>
                            onPasswordChange(event.target.value)
                        }
                        required
                        aria-invalid={Boolean(error)}
                        aria-describedby={
                            error ? "student-login-error" : undefined
                        }
                    />
                </Field>
                {error && (
                    <FieldError id="student-login-error">{error}</FieldError>
                )}
                <Button
                    className="py-7 text-base"
                    type="submit"
                    disabled={isBusy}
                >
                    {isBusy && (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    )}
                    {t(isBusy ? "signing-in" : "login")}
                </Button>
            </FieldGroup>
        </form>
    )
}

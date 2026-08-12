import { Button } from "@/components/ui/button"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"
import { LoaderCircle } from "lucide-react"
import type { FormEvent } from "react"
import { useTranslation } from "react-i18next"

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
        <form
            className="flex w-full max-w-md flex-col gap-5 rounded-2xl border bg-secondary px-6 py-10 shadow-lg sm:px-10 sm:py-15"
            onSubmit={onSubmit}
        >
            <div className="flex flex-col gap-2">
                <h1 className="text-center text-4xl font-extrabold">
                    {t("student-login-title")}
                </h1>
                <p className="text-center font-light">
                    {t("student-login-instructions")}
                </p>
            </div>
            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="student-login-id">
                        {t("student-id")}
                    </FieldLabel>
                    <Input
                        id="student-login-id"
                        className="h-12"
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
                        className="h-12"
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
                    className="h-12 text-base shadow"
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

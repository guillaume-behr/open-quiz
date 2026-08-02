import { Button } from "@/components/ui/button"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { GraduationCap, LoaderCircle } from "lucide-react"
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
            className="flex w-full max-w-md flex-col gap-5 rounded-2xl border bg-secondary px-6 py-10 shadow-lg sm:px-10 sm:py-14"
            onSubmit={onSubmit}
        >
            <div className="flex flex-col items-center gap-2 text-center">
                <div className="rounded-2xl bg-primary/10 p-3 text-primary">
                    <GraduationCap className="size-9" />
                </div>
                <h1 className="text-4xl font-extrabold">
                    {t("student-login-title")}
                </h1>
                <p className="font-light">{t("student-login-instructions")}</p>
            </div>
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
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="student-login-password">
                        {t("login-password")}
                    </FieldLabel>
                    <Input
                        id="student-login-password"
                        className="py-6"
                        type="password"
                        autoComplete="current-password"
                        value={password}
                        onChange={(event) =>
                            onPasswordChange(event.target.value)
                        }
                        required
                    />
                </Field>
                {error && <FieldError>{error}</FieldError>}
                <Button
                    className="py-7 text-base"
                    type="submit"
                    disabled={isBusy}
                >
                    {isBusy ? (
                        <LoaderCircle className="animate-spin" />
                    ) : (
                        <GraduationCap />
                    )}
                    {t(isBusy ? "signing-in" : "login")}
                </Button>
            </FieldGroup>
        </form>
    )
}

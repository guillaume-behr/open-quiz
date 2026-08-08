import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { errorMessage } from "@/lib/errors"
import { LoaderCircle } from "lucide-react"
import { useState, type SyntheticEvent } from "react"
import { useTranslation } from "react-i18next"

type DashboardLoginProps = {
    onLogin: (username: string, password: string) => Promise<void>
    title?: string
    instructions?: string
}

export function DashboardLogin({
    onLogin,
    title,
    instructions,
}: DashboardLoginProps) {
    const { t } = useTranslation()
    const [error, setError] = useState("")
    const [isSubmitting, setIsSubmitting] = useState(false)

    async function handleLogin(event: SyntheticEvent<HTMLFormElement>) {
        event.preventDefault()
        setError("")
        setIsSubmitting(true)
        const form = new FormData(event.currentTarget)
        try {
            await onLogin(
                String(form.get("login")),
                String(form.get("password"))
            )
        } catch (caught) {
            setError(errorMessage(caught, t("login-error")))
        } finally {
            setIsSubmitting(false)
        }
    }

    return (
        <form
            onSubmit={handleLogin}
            className="flex w-full max-w-md flex-col gap-5 rounded-2xl border bg-secondary px-6 py-10 shadow-lg sm:px-10 sm:py-15"
        >
            <div className="flex flex-col gap-2">
                <h1 className="text-center text-4xl font-extrabold">
                    {title ?? t("login")}
                </h1>
                <p className="text-center font-light">
                    {instructions ?? t("login-instructions")}
                </p>
            </div>

            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="login">{t("login-id")}</FieldLabel>
                    <Input
                        className="py-6"
                        id="login"
                        name="login"
                        autoComplete="username"
                        spellCheck={false}
                        required
                        aria-invalid={Boolean(error)}
                        onChange={() => setError("")}
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="password">
                        {t("login-password")}
                    </FieldLabel>
                    <Input
                        className="py-6"
                        id="password"
                        name="password"
                        autoComplete="current-password"
                        spellCheck={false}
                        type="password"
                        required
                        aria-invalid={Boolean(error)}
                        onChange={() => setError("")}
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
                    disabled={isSubmitting}
                >
                    {isSubmitting && (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    )}
                    {isSubmitting ? t("signing-in") : t("sign-in")}
                </Button>
            </FieldGroup>
        </form>
    )
}

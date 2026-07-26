
import { useTranslation } from "react-i18next"

import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { SyntheticEvent } from "react"

export function DashboardLogin() {
    const { t } = useTranslation()

    function handleLogin(event: SyntheticEvent<HTMLFormElement>) {
        event.preventDefault();

    }

    return(
        <form onSubmit={handleLogin} className="flex w-full max-w-fit min-w-sm flex-col gap-5 rounded-2xl border bg-secondary px-10 py-15 shadow-lg">
            <div className="flex flex-col gap-2">
                <p className="text-center text-4xl font-extrabold">
                    {t("login")}
                </p>
                <p className="text-center font-light">
                    {t("login-instructions")}
                </p>
            </div>

            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="login">
                        {t("login-id")}
                    </FieldLabel>
                    <Input
                        className="py-6"
                        id="login"
                        name="login"
                        autoComplete="username"
                        spellCheck={false}
                        required
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="password">{t("login-password")}</FieldLabel>
                    <Input
                        className="py-6"
                        id="password"
                        name="password"
                        autoComplete="off"
                        spellCheck={false}
                        type="password"
                        required
                    />
                </Field>

                <Button className="text-md py-7 shadow" type="submit">
                    {t("sign-in")}
                </Button>
            </FieldGroup>
        </form>
    )
}
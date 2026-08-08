import type { TwoFactorChallenge } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { errorMessage } from "@/lib/errors"
import { LoaderCircle, ShieldCheck } from "lucide-react"
import { QRCodeSVG } from "qrcode.react"
import { useState, type SyntheticEvent } from "react"
import { useTranslation } from "react-i18next"

type TwoFactorFormProps = {
    challenge: TwoFactorChallenge
    onVerify: (code: string) => Promise<void>
    onCancel: () => void
}

export function TwoFactorForm({
    challenge,
    onVerify,
    onCancel,
}: TwoFactorFormProps) {
    const { t } = useTranslation()
    const [error, setError] = useState("")
    const [isSubmitting, setIsSubmitting] = useState(false)
    const isSetup = challenge.status === "setup_required"

    async function handleSubmit(event: SyntheticEvent<HTMLFormElement>) {
        event.preventDefault()
        setError("")
        setIsSubmitting(true)
        const form = new FormData(event.currentTarget)
        try {
            await onVerify(String(form.get("code")))
        } catch (caught) {
            setError(errorMessage(caught, t("two-factor-error")))
        } finally {
            setIsSubmitting(false)
        }
    }

    return (
        <form
            onSubmit={handleSubmit}
            className="flex w-full max-w-md flex-col gap-5 rounded-2xl border bg-secondary px-8 py-10 shadow-lg"
        >
            <div className="flex flex-col items-center gap-2 text-center">
                <div className="rounded-full bg-primary/10 p-3 text-primary">
                    <ShieldCheck className="size-7" />
                </div>
                <h1 className="text-3xl font-extrabold">
                    {t(isSetup ? "two-factor-setup-title" : "two-factor-title")}
                </h1>
                <p className="text-sm text-muted-foreground">
                    {t(
                        isSetup
                            ? "two-factor-setup-instructions"
                            : "two-factor-instructions"
                    )}
                </p>
            </div>

            {isSetup && challenge.provisioning_uri && challenge.secret && (
                <div className="flex flex-col items-center gap-3">
                    <div className="rounded-xl bg-white p-3" aria-hidden="true">
                        <QRCodeSVG
                            value={challenge.provisioning_uri}
                            size={180}
                            level="M"
                        />
                    </div>
                    <div className="w-full rounded-lg border bg-background p-3 text-center">
                        <p className="text-xs text-muted-foreground">
                            {t("two-factor-manual-key")}
                        </p>
                        <code className="mt-1 block text-sm font-semibold break-all">
                            {challenge.secret}
                        </code>
                    </div>
                </div>
            )}

            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="two-factor-code">
                        {t("two-factor-code")}
                    </FieldLabel>
                    <Input
                        id="two-factor-code"
                        name="code"
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        pattern="[0-9]{6}"
                        minLength={6}
                        maxLength={6}
                        placeholder="000000"
                        className="py-6 text-center text-xl tracking-[0.35em]"
                        autoFocus
                        aria-invalid={Boolean(error)}
                        aria-describedby={
                            error ? "two-factor-error" : undefined
                        }
                        onChange={() => setError("")}
                        required
                    />
                </Field>

                {error && (
                    <p
                        id="two-factor-error"
                        className="text-sm text-destructive"
                        role="alert"
                    >
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
                    {isSubmitting
                        ? t("two-factor-verifying")
                        : t("two-factor-continue")}
                </Button>
                <Button
                    className="text-md py-7 shadow"
                    type="button"
                    variant="ghost"
                    onClick={onCancel}
                >
                    {t("back-to-login")}
                </Button>
            </FieldGroup>
        </form>
    )
}

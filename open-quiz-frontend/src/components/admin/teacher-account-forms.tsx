import type { User } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { PasswordInput } from "@/components/ui/password-input"
import { LoaderCircle, KeyRound, UserPlus } from "lucide-react"
import { type SyntheticEvent } from "react"
import { useTranslation } from "react-i18next"
import { USERNAME_PATTERN } from "@/lib/input-patterns"

/** The form an administrator creates a teacher account with. */
export function CreateTeacherForm({
    error,
    success,
    isCreating,
    onSubmit,
}: {
    error: string | null
    success: string
    isCreating: boolean
    onSubmit: (event: SyntheticEvent<HTMLFormElement>) => void
}) {
    const { t } = useTranslation()
    return (
        <form
            onSubmit={onSubmit}
            className="h-fit rounded-2xl border bg-card p-4 shadow-sm sm:p-5"
        >
            <div className="mb-5 flex items-center gap-3">
                <div className="rounded-xl bg-primary/10 p-2 text-primary">
                    <UserPlus />
                </div>
                <div>
                    <h2 className="text-xl font-bold">{t("create-user")}</h2>
                    <p className="text-sm text-muted-foreground">
                        {t("create-user-help")}
                    </p>
                </div>
            </div>

            <FieldGroup className="gap-4">
                <Field>
                    <FieldLabel htmlFor="displayName">
                        {t("display-name")}
                    </FieldLabel>
                    <Input
                        id="displayName"
                        name="displayName"
                        required
                        maxLength={120}
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="username">{t("login-id")}</FieldLabel>
                    <Input
                        id="username"
                        name="username"
                        required
                        minLength={3}
                        maxLength={80}
                        pattern={USERNAME_PATTERN}
                        autoComplete="off"
                    />
                </Field>
                <Field>
                    <FieldLabel htmlFor="new-password">
                        {t("login-password")}
                    </FieldLabel>
                    <PasswordInput
                        id="new-password"
                        name="password"
                        required
                        minLength={16}
                        maxLength={256}
                        autoComplete="new-password"
                    />
                    <p className="text-xs text-muted-foreground">
                        {t("password-help")}
                    </p>
                </Field>
                {error && (
                    <p className="text-sm text-destructive" role="alert">
                        {error}
                    </p>
                )}
                {success && (
                    <p className="text-sm text-success" role="status">
                        {success}
                    </p>
                )}

                <Button type="submit" disabled={isCreating}>
                    {isCreating ? (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    ) : (
                        <UserPlus />
                    )}
                    {isCreating ? t("creating-user") : t("create-user")}
                </Button>
            </FieldGroup>
        </form>
    )
}

/** Gives a teacher a new password and a new two-factor enrollment. */
export function AccountRecoveryDialog({
    user,
    isBusy,
    error = null,
    onClose,
    onSubmit,
}: {
    user: User | null
    isBusy: boolean
    /** Why the last reset failed, shown in the dialog that stays open. */
    error?: string | null
    onClose: () => void
    onSubmit: (event: SyntheticEvent<HTMLFormElement>) => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={user !== null}
            onOpenChange={(open) => {
                if (!open && !isBusy) onClose()
            }}
            title={t("account-recovery")}
            description={t("account-recovery-help", {
                username: user?.username,
            })}
            size="sm"
        >
            <form className="space-y-4" onSubmit={onSubmit}>
                <Field>
                    <FieldLabel htmlFor="recovery-password">
                        {t("new-password")}
                    </FieldLabel>
                    <PasswordInput
                        id="recovery-password"
                        name="password"
                        required
                        minLength={16}
                        maxLength={256}
                        autoComplete="new-password"
                    />
                    <p className="text-xs text-muted-foreground">
                        {t("account-recovery-security-help")}
                    </p>
                </Field>
                {error && <FieldError>{error}</FieldError>}
                <div className="flex justify-end gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        onClick={onClose}
                        disabled={isBusy}
                    >
                        {t("cancel")}
                    </Button>
                    <Button type="submit" disabled={isBusy}>
                        {isBusy ? (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        ) : (
                            <KeyRound />
                        )}
                        {t("reset-access")}
                    </Button>
                </div>
            </form>
        </Dialog>
    )
}

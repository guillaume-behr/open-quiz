import type { TwoFactorChallenge } from "@/api/types"
import { DashboardLogin } from "@/components/forms/dashboard-login"
import { TwoFactorForm } from "@/components/forms/two-factor-form"

type DashboardAuthenticationProps = {
    challenge: TwoFactorChallenge | null
    title: string
    instructions?: string
    // Shown above the form, such as why the user is signed out.
    notice?: string | null
    onLogin: (username: string, password: string) => Promise<void>
    onVerify: (code: string) => Promise<void>
    onCancelChallenge: () => void
}

export function DashboardAuthentication({
    challenge,
    title,
    instructions,
    notice = null,
    onLogin,
    onVerify,
    onCancelChallenge,
}: DashboardAuthenticationProps) {
    return (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 px-4">
            {notice && (
                <p
                    role="alert"
                    className="w-full max-w-md rounded-lg border border-warning/40 bg-warning/10 px-4 py-3 text-sm font-medium text-warning"
                >
                    {notice}
                </p>
            )}
            {challenge ? (
                <TwoFactorForm
                    challenge={challenge}
                    onVerify={onVerify}
                    onCancel={onCancelChallenge}
                />
            ) : (
                <DashboardLogin
                    onLogin={onLogin}
                    title={title}
                    instructions={instructions}
                />
            )}
        </div>
    )
}

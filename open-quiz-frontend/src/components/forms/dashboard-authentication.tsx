import type { TwoFactorChallenge } from "@/api/types"
import { DashboardLogin } from "@/components/forms/dashboard-login"
import { TwoFactorForm } from "@/components/forms/two-factor-form"

type DashboardAuthenticationProps = {
    challenge: TwoFactorChallenge | null
    title: string
    instructions?: string
    onLogin: (username: string, password: string) => Promise<void>
    onVerify: (code: string) => Promise<void>
    onCancelChallenge: () => void
}

export function DashboardAuthentication({
    challenge,
    title,
    instructions,
    onLogin,
    onVerify,
    onCancelChallenge,
}: DashboardAuthenticationProps) {
    return (
        <div className="flex flex-1 items-center justify-center px-4">
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

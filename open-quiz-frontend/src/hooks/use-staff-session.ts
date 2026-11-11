import { login, logout, restoreSession, verifyTwoFactor } from "@/api/auth"
import { onSessionExpired } from "@/api/client"
import type { TwoFactorChallenge, User } from "@/api/types"
import { useCallback, useEffect, useState } from "react"

export type StaffAudience = "professor" | "admin"

export type StaffSession = {
    user: User | null
    challenge: TwoFactorChallenge | null
    isLoading: boolean
    // The server refused to renew the session while this page was open.
    expired: boolean
    signIn: (username: string, password: string) => Promise<void>
    completeTwoFactor: (code: string) => Promise<void>
    cancelChallenge: () => void
    signOut: () => Promise<void>
}

/**
 * The teacher's or administrator's session on a staff page.
 *
 * It is restored once when the page mounts (never again on navigation or a
 * language change: each restore may rotate the refresh token), follows the
 * sign-in and two-factor steps, and drops the user as soon as the API
 * reports the session expired. Choosing where a wrong audience goes is the
 * page's job.
 */
export function useStaffSession(audience: StaffAudience): StaffSession {
    const [user, setUser] = useState<User | null>(null)
    const [challenge, setChallenge] = useState<TwoFactorChallenge | null>(null)
    const [isLoading, setIsLoading] = useState(true)
    const [expired, setExpired] = useState(false)

    useEffect(() => {
        let active = true
        restoreSession()
            .then((restored) => {
                if (active) setUser(restored)
            })
            .catch(() => {
                if (active) setUser(null)
            })
            .finally(() => {
                if (active) setIsLoading(false)
            })
        return () => {
            active = false
        }
    }, [])

    useEffect(
        () =>
            onSessionExpired(() => {
                setUser(null)
                setChallenge(null)
                setExpired(true)
            }),
        []
    )

    const signedIn = useCallback((signedInUser: User) => {
        setChallenge(null)
        setExpired(false)
        setUser(signedInUser)
    }, [])

    const signIn = useCallback(
        async (username: string, password: string) => {
            const result = await login(username, password, audience)
            if (result.status === "authenticated") signedIn(result.user)
            else setChallenge(result)
        },
        [audience, signedIn]
    )

    const completeTwoFactor = useCallback(
        async (code: string) => {
            if (!challenge) return
            signedIn(await verifyTwoFactor(challenge.challenge_token, code))
        },
        [challenge, signedIn]
    )

    const signOut = useCallback(async () => {
        await logout()
        setUser(null)
    }, [])

    return {
        user,
        challenge,
        isLoading,
        expired,
        signIn,
        completeTwoFactor,
        cancelChallenge: () => setChallenge(null),
        signOut,
    }
}

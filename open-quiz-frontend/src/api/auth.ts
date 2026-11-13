import {
    clearSessionTokens,
    refreshProofHeaders,
    request,
    requestParsed,
    restoreAccessToken,
    setSessionTokens,
} from "./client"
import { LoginResponseSchema, TokenResponseSchema, UserSchema } from "./schemas"
import type { TwoFactorChallenge, User } from "./types"

/** A browser that passed two-factor login today signs in without a code. */
type LoginResult = TwoFactorChallenge | { status: "authenticated"; user: User }

export async function login(
    username: string,
    password: string,
    audience: "professor" | "admin"
): Promise<LoginResult> {
    const result = await requestParsed(
        LoginResponseSchema,
        "/api/auth/login",
        {
            method: "POST",
            body: JSON.stringify({ username, password, audience }),
        },
        false
    )
    if (result.status !== "authenticated") return result
    setSessionTokens(result.access_token, result.refresh_proof)
    return { status: "authenticated", user: await currentUser() }
}

/** Decides when "today" ends for the browser trusted after this login. */
function browserTimeZone(): string | undefined {
    try {
        return Intl.DateTimeFormat().resolvedOptions().timeZone || undefined
    } catch {
        return undefined
    }
}

export async function verifyTwoFactor(
    challengeToken: string,
    code: string
): Promise<User> {
    const result = await requestParsed(
        TokenResponseSchema,
        "/api/auth/2fa/verify",
        {
            method: "POST",
            body: JSON.stringify({
                challenge_token: challengeToken,
                code,
                timezone: browserTimeZone(),
            }),
        },
        false
    )
    setSessionTokens(result.access_token, result.refresh_proof)
    return currentUser()
}

export async function restoreSession(): Promise<User> {
    if (!(await restoreAccessToken())) {
        throw new Error("No active session")
    }
    return currentUser()
}

/**
 * A plain sign-out keeps this browser trusted for the rest of the day;
 * `forgetBrowser` also asks for the two-factor code again at the next login.
 */
export async function logout({
    forgetBrowser = false,
}: { forgetBrowser?: boolean } = {}): Promise<boolean> {
    // Resolves to whether the server confirmed: only then are the session
    // cookies gone from this browser.
    try {
        await request<void>(
            "/api/auth/logout",
            {
                method: "POST",
                headers: refreshProofHeaders(),
                ...(forgetBrowser
                    ? { body: JSON.stringify({ forget_browser: true }) }
                    : {}),
            },
            false
        )
        return true
    } catch {
        // Local credentials must still be discarded when the API is offline.
        return false
    } finally {
        clearSessionTokens()
    }
}

function currentUser(): Promise<User> {
    return requestParsed(UserSchema, "/api/users/me")
}

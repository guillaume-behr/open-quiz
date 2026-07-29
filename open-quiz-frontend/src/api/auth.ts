import { request, restoreAccessToken, setAccessToken } from "./client"
import type { TwoFactorChallenge, User } from "./types"

type TokenResponse = {
    access_token: string
}

export async function login(
    username: string,
    password: string,
    audience: "professor" | "admin"
): Promise<TwoFactorChallenge> {
    setAccessToken(null)
    return request<TwoFactorChallenge>(
        "/api/auth/login",
        {
            method: "POST",
            body: JSON.stringify({ username, password, audience }),
        },
        false
    )
}

export async function verifyTwoFactor(
    challengeToken: string,
    code: string
): Promise<User> {
    const result = await request<TokenResponse>(
        "/api/auth/2fa/verify",
        {
            method: "POST",
            body: JSON.stringify({
                challenge_token: challengeToken,
                code,
            }),
        },
        false
    )
    setAccessToken(result.access_token)
    return currentUser()
}

export async function restoreSession(): Promise<User> {
    if (!(await restoreAccessToken())) {
        throw new Error("No active session")
    }
    return currentUser()
}

export async function logout(): Promise<void> {
    try {
        await request<void>("/api/auth/logout", { method: "POST" }, false)
    } finally {
        setAccessToken(null)
    }
}

function currentUser(): Promise<User> {
    return request<User>("/api/users/me")
}

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000"

let accessToken: string | null = null
let refreshPromise: Promise<boolean> | null = null

export type User = {
    id: number
    username: string
    display_name: string
    is_admin: boolean
    is_active: boolean
    created_at: string
}

export type NewUser = {
    username: string
    display_name: string
    password: string
}

type TokenResponse = {
    access_token: string
}

export type TwoFactorChallenge = {
    status: "setup_required" | "verification_required"
    challenge_token: string
    secret: string | null
    provisioning_uri: string | null
}

async function errorFrom(response: Response): Promise<Error> {
    const body = (await response.json().catch(() => ({}))) as {
        detail?: string
    }
    return new Error(body.detail ?? "Une erreur est survenue.")
}

async function refreshAccessToken(): Promise<boolean> {
    if (!refreshPromise) {
        refreshPromise = fetch(`${API_URL}/api/auth/refresh`, {
            method: "POST",
            credentials: "include",
        })
            .then(async (response) => {
                if (!response.ok) {
                    accessToken = null
                    return false
                }
                const result = (await response.json()) as TokenResponse
                accessToken = result.access_token
                return true
            })
            .finally(() => {
                refreshPromise = null
            })
    }
    return refreshPromise
}

async function request<T>(
    path: string,
    options: RequestInit = {},
    allowRefresh = true
): Promise<T> {
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
            ...options.headers,
        },
    })

    if (
        response.status === 401 &&
        allowRefresh &&
        (await refreshAccessToken())
    ) {
        return request<T>(path, options, false)
    }
    if (!response.ok) {
        throw await errorFrom(response)
    }
    if (response.status === 204) {
        return undefined as T
    }
    return response.json() as Promise<T>
}

export async function login(
    username: string,
    password: string
): Promise<TwoFactorChallenge> {
    accessToken = null
    return request<TwoFactorChallenge>(
        "/api/auth/login",
        {
            method: "POST",
            body: JSON.stringify({ username, password }),
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
    accessToken = result.access_token
    return currentUser()
}

export function restoreSession(): Promise<User> {
    return currentUser()
}

export async function logout(): Promise<void> {
    try {
        await request<void>("/api/auth/logout", { method: "POST" }, false)
    } finally {
        accessToken = null
    }
}

function currentUser(): Promise<User> {
    return request<User>("/api/users/me")
}

export function getUsers(): Promise<User[]> {
    return request<User[]>("/api/admin/users")
}

export function createUser(user: NewUser): Promise<User> {
    return request<User>("/api/admin/users", {
        method: "POST",
        body: JSON.stringify(user),
    })
}

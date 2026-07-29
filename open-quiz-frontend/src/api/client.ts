const API_URL = import.meta.env.VITE_API_URL ?? ""

let accessToken: string | null = null
let refreshPromise: Promise<boolean> | null = null

type TokenResponse = {
    access_token: string
}

export class ApiError extends Error {
    readonly status: number

    constructor(message: string, status: number) {
        super(message)
        this.name = "ApiError"
        this.status = status
    }
}

async function errorFrom(response: Response): Promise<Error> {
    const body = (await response.json().catch(() => ({}))) as {
        detail?: string
    }
    return new ApiError(
        body.detail ?? "Une erreur est survenue.",
        response.status
    )
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

export function restoreAccessToken(): Promise<boolean> {
    return refreshAccessToken()
}

export function setAccessToken(token: string | null) {
    accessToken = token
}

function requestHeaders(
    options: RequestInit,
    includeAccessToken = true
): HeadersInit {
    const isFormData = options.body instanceof FormData
    return {
        ...(options.body !== undefined && !isFormData
            ? { "Content-Type": "application/json" }
            : {}),
        ...(includeAccessToken && accessToken
            ? { Authorization: `Bearer ${accessToken}` }
            : {}),
        ...options.headers,
    }
}

export async function request<T>(
    path: string,
    options: RequestInit = {},
    allowRefresh = true
): Promise<T> {
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        credentials: "include",
        headers: requestHeaders(options),
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

export async function requestBlob(
    path: string,
    options: RequestInit = {},
    allowRefresh = true,
    includeAccessToken = true
): Promise<Blob> {
    const response = await fetch(`${API_URL}${path}`, {
        ...options,
        credentials: "include",
        headers: requestHeaders(options, includeAccessToken),
    })
    if (
        response.status === 401 &&
        allowRefresh &&
        (await refreshAccessToken())
    ) {
        return requestBlob(path, options, false, includeAccessToken)
    }
    if (!response.ok) {
        throw await errorFrom(response)
    }
    return response.blob()
}

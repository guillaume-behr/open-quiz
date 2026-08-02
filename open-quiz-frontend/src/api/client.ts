const API_URL = import.meta.env.VITE_API_URL ?? ""
const REFRESH_PROOF_STORAGE_KEY = "open-quiz-refresh-proof"

let accessToken: string | null = null
let refreshProof: string | null = readRefreshProof()
let refreshPromise: Promise<boolean> | null = null

type TokenResponse = {
    access_token: string
    refresh_proof: string
}

export class ApiError extends Error {
    readonly status: number

    constructor(message: string, status: number) {
        super(message)
        this.name = "ApiError"
        this.status = status
    }
}

function readRefreshProof(): string | null {
    try {
        return sessionStorage.getItem(REFRESH_PROOF_STORAGE_KEY)
    } catch {
        return null
    }
}

function storeRefreshProof(proof: string | null) {
    refreshProof = proof
    try {
        if (proof) {
            sessionStorage.setItem(REFRESH_PROOF_STORAGE_KEY, proof)
        } else {
            sessionStorage.removeItem(REFRESH_PROOF_STORAGE_KEY)
        }
    } catch {
        // Memory-only authentication still works when storage is unavailable.
    }
}

async function errorFrom(response: Response): Promise<Error> {
    const body = (await response.json().catch(() => ({}))) as {
        detail?: unknown
    }
    // FastAPI validation failures return `detail` as an array of issues.
    const detail = typeof body.detail === "string" ? body.detail : null
    return new ApiError(detail ?? "Une erreur est survenue.", response.status)
}

async function refreshAccessToken(): Promise<boolean> {
    if (!refreshProof) return false
    if (!refreshPromise) {
        refreshPromise = fetch(`${API_URL}/api/auth/refresh`, {
            method: "POST",
            credentials: "include",
            headers: { "X-Refresh-Proof": refreshProof },
        })
            .then(async (response) => {
                if (!response.ok) {
                    clearSessionTokens()
                    return false
                }
                const result = (await response.json()) as TokenResponse
                setSessionTokens(result.access_token, result.refresh_proof)
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

export function setSessionTokens(access: string, proof: string) {
    accessToken = access
    storeRefreshProof(proof)
}

export function clearSessionTokens() {
    accessToken = null
    storeRefreshProof(null)
}

export function refreshProofHeaders(): HeadersInit {
    return refreshProof ? { "X-Refresh-Proof": refreshProof } : {}
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

export async function requestPage<T>(
    path: string,
    options: RequestInit = {},
    allowRefresh = true
): Promise<import("./types").Page<T>> {
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
        return requestPage<T>(path, options, false)
    }
    if (!response.ok) throw await errorFrom(response)

    const items = (await response.json()) as T[]
    const page = Number(response.headers.get("X-Page") ?? 1)
    const pageSize = Number(
        response.headers.get("X-Page-Size") ?? Math.max(items.length, 1)
    )
    const total = Number(response.headers.get("X-Total-Count") ?? items.length)
    return {
        items,
        page,
        pageSize,
        total,
        totalPages: Math.max(1, Math.ceil(total / pageSize)),
    }
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

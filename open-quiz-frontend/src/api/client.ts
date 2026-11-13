import * as v from "valibot"

import { TokenResponseSchema } from "./schemas"

const API_URL = import.meta.env.VITE_API_URL ?? ""
const REFRESH_PROOF_STORAGE_KEY = "open-quiz-refresh-proof"
const REQUEST_TIMEOUT_MS = 30_000
/** For uploads, imports and downloads, which can take longer. */
export const LARGE_REQUEST_TIMEOUT_MS = 120_000

/**
 * Options of a request. The timeout applies to each attempt, a retry after
 * a token refresh included, and also when the caller passes its own signal.
 */
export type RequestOptions = RequestInit & { timeoutMs?: number }

function requestSignal(
    signal?: AbortSignal | null,
    timeoutMs = REQUEST_TIMEOUT_MS
): AbortSignal {
    const timeout = AbortSignal.timeout(timeoutMs)
    return signal ? AbortSignal.any([signal, timeout]) : timeout
}

let accessToken: string | null = null
let refreshProof: string | null = readRefreshProof()
let refreshPromise: Promise<boolean> | null = null
const sessionExpiredListeners = new Set<() => void>()

/**
 * Run `listener` when the server refuses to renew the staff session (it
 * expired, or was revoked elsewhere), so the open page can return to its
 * sign-in form instead of failing every action. Returns the unsubscriber.
 */
export function onSessionExpired(listener: () => void): () => void {
    sessionExpiredListeners.add(listener)
    return () => {
        sessionExpiredListeners.delete(listener)
    }
}

/**
 * The code of an ApiError for a response that does not have the shape the
 * interface expects: the server is not the version this interface was built
 * for, or something between them altered the response.
 */
export const UNEXPECTED_RESPONSE_CODE = "UNEXPECTED_RESPONSE"

export class ApiError extends Error {
    readonly status: number
    readonly detail: unknown
    readonly code: string | null

    constructor(message: string, status: number, detail?: unknown) {
        super(message)
        this.name = "ApiError"
        this.status = status
        this.detail = detail
        this.code =
            typeof detail === "object" &&
            detail !== null &&
            "code" in detail &&
            typeof detail.code === "string"
                ? detail.code
                : null
    }
}

/**
 * The response body as `schema` describes it, or an ApiError with
 * UNEXPECTED_RESPONSE_CODE: a malformed body never reaches the screens.
 */
export function parseResponse<S extends v.GenericSchema>(
    schema: S,
    body: unknown,
    status = 200
): v.InferOutput<S> {
    const result = v.safeParse(schema, body)
    if (result.success) return result.output
    throw new ApiError("Unexpected response from the server", status, {
        code: UNEXPECTED_RESPONSE_CODE,
        issues: v.flatten(result.issues),
    })
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
    const code =
        typeof body.detail === "object" &&
        body.detail !== null &&
        "code" in body.detail &&
        typeof body.detail.code === "string"
            ? body.detail.code
            : null
    return new ApiError(
        // Never shown as is: screens show apiErrorMessage, a translated text.
        detail ?? code ?? `Request failed with status ${response.status}`,
        response.status,
        body.detail
    )
}

async function refreshAccessToken(): Promise<boolean> {
    if (!refreshProof) return false
    if (!refreshPromise) {
        refreshPromise = fetch(`${API_URL}/api/auth/refresh`, {
            method: "POST",
            credentials: "include",
            signal: requestSignal(),
            headers: { "X-Refresh-Proof": refreshProof },
        })
            .then(async (response) => {
                if (response.status === 401 || response.status === 403) {
                    clearSessionTokens()
                    for (const listener of sessionExpiredListeners) listener()
                    return false
                }
                if (!response.ok) throw await errorFrom(response)
                const result = parseResponse(
                    TokenResponseSchema,
                    await response.json(),
                    response.status
                )
                setSessionTokens(result.access_token, result.refresh_proof)
                return true
            })
            .finally(() => {
                refreshPromise = null
            })
    }
    return refreshPromise
}

/** Seconds since the epoch at which a JWT expires, or null if unreadable. */
function tokenExpiry(token: string): number | null {
    try {
        const payload = token.split(".")[1]
        if (!payload) return null
        const claims = JSON.parse(
            atob(payload.replace(/-/g, "+").replace(/_/g, "/"))
        ) as { exp?: unknown }
        return typeof claims.exp === "number" ? claims.exp : null
    } catch {
        return null
    }
}

/**
 * Make sure a staff session is usable, renewing it only when needed.
 *
 * Every renewal rotates the refresh token, and the server revokes the whole
 * session if an old one comes back (another tab, a race): an access token
 * still in memory is used as it is unless it is known to expire within a
 * minute, and a 401 on the next request renews it then.
 */
export function restoreAccessToken(): Promise<boolean> {
    if (accessToken) {
        const expiry = tokenExpiry(accessToken)
        if (expiry === null || expiry * 1000 - Date.now() > 60_000)
            return Promise.resolve(true)
    }
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

export async function getLiveAccessToken(
    forceRefresh = false
): Promise<string | null> {
    if ((forceRefresh || !accessToken) && !(await refreshAccessToken()))
        return null
    return accessToken
}

export function apiWebSocketUrl(path: string): string {
    const base = new URL(
        API_URL || window.location.origin,
        window.location.origin
    )
    const url = new URL(path, base)
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
    return url.toString()
}

export function refreshProofHeaders(): HeadersInit {
    return refreshProof ? { "X-Refresh-Proof": refreshProof } : {}
}

function requestHeaders(
    options: RequestOptions,
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

async function authenticatedFetch(
    path: string,
    options: RequestOptions,
    allowRefresh: boolean,
    includeAccessToken = true
): Promise<Response> {
    const { timeoutMs, ...init } = options
    // Built for each attempt, so a retry gets a full timeout of its own.
    const response = await fetch(`${API_URL}${path}`, {
        ...init,
        signal: requestSignal(init.signal, timeoutMs),
        credentials: "include",
        headers: requestHeaders(options, includeAccessToken),
    })
    if (
        response.status === 401 &&
        allowRefresh &&
        (await refreshAccessToken())
    ) {
        return authenticatedFetch(path, options, false, includeAccessToken)
    }
    if (!response.ok) {
        throw await errorFrom(response)
    }
    return response
}

export async function request<T>(
    path: string,
    options: RequestOptions = {},
    allowRefresh = true
): Promise<T> {
    const response = await authenticatedFetch(path, options, allowRefresh)
    if (response.status === 204) {
        return undefined as T
    }
    return response.json() as Promise<T>
}

/** A request whose response is checked against `schema` before it is used. */
export async function requestParsed<S extends v.GenericSchema>(
    schema: S,
    path: string,
    options: RequestOptions = {},
    allowRefresh = true
): Promise<v.InferOutput<S>> {
    const response = await authenticatedFetch(path, options, allowRefresh)
    // An unreadable body is as unexpected as a body of the wrong shape.
    const body: unknown = await response.json().catch(() => undefined)
    return parseResponse(schema, body, response.status)
}

export async function requestPage<T>(
    path: string,
    options: RequestOptions = {},
    allowRefresh = true
): Promise<import("./types").Page<T>> {
    const response = await authenticatedFetch(path, options, allowRefresh)

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
    options: RequestOptions = {},
    allowRefresh = true,
    includeAccessToken = true
): Promise<Blob> {
    const response = await authenticatedFetch(
        path,
        { timeoutMs: LARGE_REQUEST_TIMEOUT_MS, ...options },
        allowRefresh,
        includeAccessToken
    )
    return response.blob()
}

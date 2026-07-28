import { ApiError } from "@/api/client"

export function errorMessage(error: unknown, fallback: string): string {
    if (error instanceof ApiError) return fallback
    return error instanceof Error ? error.message : fallback
}

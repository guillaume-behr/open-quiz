import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs))
}

export function isRtlLanguage(language: string | null | undefined): boolean {
    return Boolean(language && /^ar(?:\b|-)/i.test(language))
}

export function naturalCompare(first: string, second: string): number {
    return first.localeCompare(second, undefined, {
        numeric: true,
        sensitivity: "base",
    })
}

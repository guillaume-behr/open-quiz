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

export function formatClassName(
    gradeLevel: string | null | undefined,
    className: string | null | undefined
): string {
    const level = gradeLevel?.trim().replace(/\s+/g, " ") ?? ""
    const name = className?.trim().replace(/\s+/g, " ") ?? ""
    if (!level) return name
    if (!name) return level
    const normalizedLevel = level.toLocaleLowerCase()
    const normalizedName = name.toLocaleLowerCase()
    if (normalizedName === normalizedLevel) return name
    for (const separator of [" - ", " — ", " · "]) {
        const suffix = `${separator}${normalizedLevel}`
        if (normalizedName.endsWith(suffix)) {
            return `${level} ${name.slice(0, -suffix.length).trim()}`
        }
        const prefix = `${normalizedLevel}${separator}`
        if (normalizedName.startsWith(prefix)) {
            return `${level} ${name.slice(prefix.length).trim()}`
        }
    }
    if (normalizedName.startsWith(`${normalizedLevel} `)) return name
    return `${level} ${name}`
}

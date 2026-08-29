import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
    return twMerge(clsx(inputs))
}

export function isRtlLanguage(language: string | null | undefined): boolean {
    return Boolean(language && /^ar(?:\b|-)/i.test(language))
}

/** Page number holding `id`, so a saved item stays on screen after a reload. */
export function pageContaining(
    items: readonly { id: number }[],
    id: number,
    pageSize: number
): number {
    const index = items.findIndex((item) => item.id === id)
    return index < 0 ? 1 : Math.floor(index / pageSize) + 1
}

/** Hand a generated file to the browser. The link must be in the document for
 * the click to start a download in every supported browser. */
export function saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob)
    const link = document.createElement("a")
    link.href = url
    link.download = filename
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
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

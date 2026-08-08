const scoreFormatters = new Map<string, Intl.NumberFormat>()

export function formatScore(score: number, locale: string): string {
    let formatter = scoreFormatters.get(locale)
    if (!formatter) {
        formatter = new Intl.NumberFormat(locale, {
            maximumFractionDigits: 2,
        })
        scoreFormatters.set(locale, formatter)
    }
    return formatter.format(score)
}

export function resultStart(result: {
    started_at: string | null
    created_at: string
}): Date {
    return new Date(result.started_at ?? result.created_at)
}

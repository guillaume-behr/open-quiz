/**
 * Quizzes are marked out of whatever their questions are worth, which changes
 * from one paper to the next. Grades are shown on a single scale so that two
 * results can be compared at a glance; the points they come from stay one
 * hover away.
 */
export const GRADE_SCALE = 20

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

/**
 * A score rebased on {@link GRADE_SCALE}, or null for a paper that carries no
 * points at all: there is no grade to compute out of nothing.
 */
export function gradeOnScale(
    score: number,
    maximumScore: number
): number | null {
    if (!Number.isFinite(score) || !Number.isFinite(maximumScore)) return null
    if (maximumScore <= 0) return null
    return (score / maximumScore) * GRADE_SCALE
}

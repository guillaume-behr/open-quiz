import { getQuizResults, type QuizResultQuery } from "@/api/quizzes"
import type { QuizSession } from "@/api/types"
import type { ResultFilterValues } from "./result-card"
import {
    addDays,
    DAYS_PER_WEEK,
    resultStart,
    startOfWeek,
} from "./results-utils"

function resultQuery(filters: ResultFilterValues): QuizResultQuery {
    return { quizSearch: filters.quiz.trim(), classId: filters.class }
}

export function loadResults(
    page: number,
    filters: ResultFilterValues,
    _focus: unknown,
    signal: AbortSignal
) {
    return getQuizResults(page, resultQuery(filters), undefined, signal)
}

/** The most results one week of the schedule shows (the API's page cap). */
const WEEK_RESULT_LIMIT = 100

type ScheduleWeek = {
    weekStart: Date
    results: QuizSession[]
    hasEarlier: boolean
    hasLater: boolean
}

/**
 * The results of one week, the newest week holding any when `week` is
 * null, loaded by date rather than taken from the page on screen.
 */
export async function loadScheduleWeek(
    filters: ResultFilterValues,
    week: Date | null,
    signal: AbortSignal
): Promise<ScheduleWeek | null> {
    const query = resultQuery(filters)
    const newest = (await getQuizResults(1, query, 1, signal)).items[0]
    if (!newest) return null
    const latestWeek = startOfWeek(resultStart(newest))
    const weekStart = week ?? latestWeek
    const [weekResults, earlier] = await Promise.all([
        getQuizResults(
            1,
            {
                ...query,
                startedFrom: weekStart,
                startedBefore: addDays(weekStart, DAYS_PER_WEEK),
            },
            WEEK_RESULT_LIMIT,
            signal
        ),
        getQuizResults(1, { ...query, startedBefore: weekStart }, 1, signal),
    ])
    return {
        weekStart,
        results: weekResults.items,
        hasEarlier: earlier.total > 0,
        hasLater: weekStart < latestWeek,
    }
}

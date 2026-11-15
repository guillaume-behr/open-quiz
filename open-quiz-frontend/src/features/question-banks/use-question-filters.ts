import {
    QUESTION_DIFFICULTIES,
    type AnswerMode,
    type Question,
} from "@/api/types"
import { questionMaxPoints } from "@/lib/questions"
import { useMemo, useState } from "react"

const DEFAULT_QUESTION_SORT = "difficulty-asc"

/** The filters and order of a question list, as the teacher left them. */
export type QuestionFilterValues = {
    sort: string
    minimumPoints: string
    maximumPoints: string
    minimumDifficulty: string
    maximumDifficulty: string
    answerModes: AnswerMode[]
}

type Difficulty = (typeof QUESTION_DIFFICULTIES)[number]

const difficultyRank = new Map(
    QUESTION_DIFFICULTIES.map((difficulty, index) => [difficulty, index])
)

function rankOf(difficulty: string): number | null {
    return difficulty
        ? (difficultyRank.get(difficulty as Difficulty) ?? null)
        : null
}

/** The questions kept by the filters, in the chosen order. */
function filterQuestions(
    questions: Question[],
    filters: QuestionFilterValues
): Question[] {
    const { sort, answerModes } = filters
    const minPoints =
        filters.minimumPoints === "" ? null : Number(filters.minimumPoints)
    const maxPoints =
        filters.maximumPoints === "" ? null : Number(filters.maximumPoints)
    const minDifficulty = rankOf(filters.minimumDifficulty)
    const maxDifficulty = rankOf(filters.maximumDifficulty)
    const filtered = questions.filter((question) => {
        const points = questionMaxPoints(question)
        const difficulty = difficultyRank.get(question.difficulty) ?? 0
        return (
            (minPoints === null || points >= minPoints) &&
            (maxPoints === null || points <= maxPoints) &&
            (minDifficulty === null || difficulty >= minDifficulty) &&
            (maxDifficulty === null || difficulty <= maxDifficulty) &&
            (answerModes.length === 0 ||
                answerModes.includes(question.answer_mode))
        )
    })
    if (sort === "default") return filtered
    return [...filtered].sort((first, second) => {
        if (sort === "difficulty-asc" || sort === "difficulty-desc") {
            const difference =
                (difficultyRank.get(first.difficulty) ?? 0) -
                (difficultyRank.get(second.difficulty) ?? 0)
            return sort === "difficulty-asc" ? difference : -difference
        }
        const difference = questionMaxPoints(first) - questionMaxPoints(second)
        return sort === "points-asc" ? difference : -difference
    })
}

/**
 * The filter and sort state of a question list, starting from `initial`, and
 * the questions it keeps.
 */
export function useQuestionFilters(
    questions: Question[],
    initial: Partial<QuestionFilterValues> | null = null
) {
    const [sort, setSort] = useState(initial?.sort ?? DEFAULT_QUESTION_SORT)
    const [minimumPoints, setMinimumPoints] = useState(
        initial?.minimumPoints ?? ""
    )
    const [maximumPoints, setMaximumPoints] = useState(
        initial?.maximumPoints ?? ""
    )
    const [minimumDifficulty, setMinimumDifficulty] = useState(
        initial?.minimumDifficulty ?? ""
    )
    const [maximumDifficulty, setMaximumDifficulty] = useState(
        initial?.maximumDifficulty ?? ""
    )
    const [answerModes, setAnswerModes] = useState<AnswerMode[]>(
        initial?.answerModes ?? []
    )
    const visibleQuestions = useMemo(
        () =>
            filterQuestions(questions, {
                sort,
                minimumPoints,
                maximumPoints,
                minimumDifficulty,
                maximumDifficulty,
                answerModes,
            }),
        [
            answerModes,
            maximumDifficulty,
            maximumPoints,
            minimumDifficulty,
            minimumPoints,
            questions,
            sort,
        ]
    )
    const hasFilters = Boolean(
        minimumPoints ||
        maximumPoints ||
        minimumDifficulty ||
        maximumDifficulty ||
        answerModes.length
    )
    const activeCount =
        Number(sort !== DEFAULT_QUESTION_SORT) +
        Number(Boolean(minimumPoints)) +
        Number(Boolean(maximumPoints)) +
        Number(Boolean(minimumDifficulty)) +
        Number(Boolean(maximumDifficulty)) +
        answerModes.length

    function toggleAnswerMode(mode: AnswerMode) {
        setAnswerModes((current) =>
            current.includes(mode)
                ? current.filter((item) => item !== mode)
                : [...current, mode]
        )
    }

    /** Clears the filters, keeping the order. */
    function clearFilters() {
        setMinimumPoints("")
        setMaximumPoints("")
        setMinimumDifficulty("")
        setMaximumDifficulty("")
        setAnswerModes([])
    }

    return {
        values: {
            sort,
            minimumPoints,
            maximumPoints,
            minimumDifficulty,
            maximumDifficulty,
            answerModes,
        } satisfies QuestionFilterValues,
        setSort,
        setMinimumPoints,
        setMaximumPoints,
        setMinimumDifficulty,
        setMaximumDifficulty,
        toggleAnswerMode,
        clearFilters,
        visibleQuestions,
        hasFilters,
        activeCount,
    }
}

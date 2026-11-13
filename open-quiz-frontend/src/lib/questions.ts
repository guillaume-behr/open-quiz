import type { Question } from "@/api/types"

/** The most a question can earn: the points of its choices, negatives aside. */
export function questionMaxPoints(question: Pick<Question, "choices">): number {
    return question.choices.reduce(
        (total, choice) => total + Math.max(0, choice.points),
        0
    )
}

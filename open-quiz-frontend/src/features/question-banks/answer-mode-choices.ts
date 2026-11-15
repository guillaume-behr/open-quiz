import type { EditableChoice } from "./question-form-types"

let lastChoiceUid = 0

/** A client-side key for a choice row, unique for the page's lifetime. */
export function nextChoiceUid(): number {
    lastChoiceUid += 1
    return lastChoiceUid
}

/**
 * Fits choices to a choice-based answer mode without moving the answer key:
 * they are kept as they are unless single choice receives several correct
 * ones, in which case only the first correct one stays correct.
 */
export function fitChoicesToMode(
    choices: EditableChoice[],
    mode: "single" | "multiple"
): { choices: EditableChoice[]; keptFirstCorrectOnly: boolean } {
    const firstCorrectIndex = choices.findIndex((choice) => choice.is_correct)
    const correctCount = choices.filter((choice) => choice.is_correct).length
    if (mode === "multiple" || correctCount <= 1) {
        return { choices, keptFirstCorrectOnly: false }
    }
    return {
        choices: choices.map((choice, index) => ({
            ...choice,
            is_correct: index === firstCorrectIndex,
        })),
        keptFirstCorrectOnly: true,
    }
}

import type { StudentQuizQuestion } from "@/api/types"
import type { BrowserTranslator } from "@/lib/browser-translator"

export async function translateQuestion(
    translator: BrowserTranslator,
    question: StudentQuizQuestion
): Promise<StudentQuizQuestion> {
    const translatedChoices = await Promise.all(
        question.choices.map(async (choice) => ({
            ...choice,
            label: await translator.translate(choice.label),
        }))
    )

    return {
        ...question,
        prompt: await translator.translate(question.prompt),
        choices: translatedChoices,
    }
}

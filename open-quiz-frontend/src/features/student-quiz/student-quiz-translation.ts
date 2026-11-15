import type { StudentAnswerSummary, StudentQuizQuestion } from "@/api/types"
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

export async function translateAnswerSummary(
    translator: BrowserTranslator,
    summary: StudentAnswerSummary
): Promise<StudentAnswerSummary> {
    return {
        ...summary,
        prompt: await translator.translate(summary.prompt),
        // A written answer is the student's own wording: only the choice
        // labels the teacher wrote are worth translating.
        submitted_answers:
            summary.answer_mode === "written"
                ? summary.submitted_answers
                : await Promise.all(
                      summary.submitted_answers.map((answer) =>
                          translator.translate(answer)
                      )
                  ),
    }
}

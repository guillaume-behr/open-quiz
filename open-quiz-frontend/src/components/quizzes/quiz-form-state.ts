import type { QuestionBank, Quiz } from "@/api/types"

export const difficultyKeys = ["easy", "medium", "hard"] as const
export type Difficulty = (typeof difficultyKeys)[number]
export type DifficultyCounts = Record<Difficulty, number>

const NO_QUESTIONS: DifficultyCounts = { easy: 0, medium: 0, hard: 0 }

/** Draft of the quiz being created or edited in QuizFormDialog. */
export type QuizFormState = {
    editingQuiz: Quiz | null
    title: string
    gradeLevel: string
    selectedBankIds: number[]
    durationMinutes: number
    allowPreviousQuestions: boolean
    allowAnswerReview: boolean
    allowNegativePoints: boolean
    sameQuestionsForAll: boolean
    difficultyCounts: DifficultyCounts
}

type EditableField = Exclude<
    keyof QuizFormState,
    "editingQuiz" | "gradeLevel" | "selectedBankIds"
>

export type QuizFormAction =
    | { type: "reset" }
    | { type: "edit"; quiz: Quiz }
    | {
          [Field in EditableField]: {
              type: "set"
              field: Field
              value: QuizFormState[Field]
          }
      }[EditableField]
    | { type: "grade-level"; gradeLevel: string }
    | { type: "banks"; ids: number[]; banks: QuestionBank[] }

export const emptyQuizForm: QuizFormState = {
    editingQuiz: null,
    title: "",
    gradeLevel: "",
    selectedBankIds: [],
    durationMinutes: 15,
    allowPreviousQuestions: false,
    allowAnswerReview: true,
    allowNegativePoints: false,
    sameQuestionsForAll: false,
    difficultyCounts: NO_QUESTIONS,
}

export function availableQuestionCounts(
    banks: QuestionBank[],
    selectedBankIds: number[]
): DifficultyCounts {
    const selectedBanks = banks.filter((bank) =>
        selectedBankIds.includes(bank.id)
    )
    return difficultyKeys.reduce(
        (result, difficulty) => {
            result[difficulty] = selectedBanks.reduce(
                (total, bank) => total + bank[`${difficulty}_question_count`],
                0
            )
            return result
        },
        { ...NO_QUESTIONS }
    )
}

export function quizFormReducer(
    state: QuizFormState,
    action: QuizFormAction
): QuizFormState {
    switch (action.type) {
        case "reset":
            return emptyQuizForm
        case "edit": {
            const { quiz } = action
            return {
                editingQuiz: quiz,
                title: quiz.title,
                gradeLevel: quiz.question_banks[0]?.grade_level ?? "",
                selectedBankIds: quiz.question_banks.map((bank) => bank.id),
                durationMinutes: quiz.duration_seconds / 60,
                allowPreviousQuestions: quiz.allow_previous_questions,
                allowAnswerReview: quiz.allow_answer_review,
                allowNegativePoints: quiz.allow_negative_points,
                sameQuestionsForAll: quiz.same_questions_for_all,
                difficultyCounts: {
                    easy: quiz.easy_question_count,
                    medium: quiz.medium_question_count,
                    hard: quiz.hard_question_count,
                },
            }
        }
        case "set":
            return { ...state, [action.field]: action.value }
        case "grade-level":
            // Banks belong to one grade level: changing it drops the selection.
            return {
                ...state,
                gradeLevel: action.gradeLevel,
                selectedBankIds: [],
                difficultyCounts: NO_QUESTIONS,
            }
        case "banks": {
            const available = availableQuestionCounts(action.banks, action.ids)
            const counts = state.difficultyCounts
            return {
                ...state,
                selectedBankIds: action.ids,
                difficultyCounts: {
                    easy: Math.min(counts.easy, available.easy),
                    medium: Math.min(counts.medium, available.medium),
                    hard: Math.min(counts.hard, available.hard),
                },
            }
        }
    }
}

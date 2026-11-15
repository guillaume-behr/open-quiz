import type * as v from "valibot"

import type { components } from "./openapi"
import type {
    CODE_LANGUAGES,
    StudentAnswerSummarySchema,
    StudentQuizJoinSchema,
    StudentQuizQuestionSchema,
    StudentQuizSessionSchema,
    TrainingFeedbackSchema,
    TwoFactorChallengeSchema,
    UserSchema,
} from "./schemas"

// The API's bodies, generated from the schema the backend exports
// (pnpm generate:api-types), so that they cannot drift from it. The
// responses checked at runtime take their type from their valibot schema
// instead (./schemas).
type Schemas = components["schemas"]

export type User = v.InferOutput<typeof UserSchema>

export type Page<T> = {
    items: T[]
    page: number
    pageSize: number
    total: number
    totalPages: number
}

export type NewUser = Schemas["UserCreate"]

export type ProblemReport = Schemas["ProblemReportResponse"]

export type StudentAccount = Schemas["StudentAccountResponse"]
export type CreatedStudentAccount = Schemas["StudentAccountCreatedResponse"]
export type StudentCredential = Schemas["StudentCredentialResponse"]
export type StudentClass = Schemas["StudentClassResponse"]
export type GradeLevel = Schemas["GradeLevelResponse"]

export type QuestionBank = Schemas["QuestionBankResponse"]
export type NewQuestionBank = Schemas["QuestionBankCreate"]
export type QuestionBankImportResult = Schemas["QuestionBatchImportResponse"]

export const QUESTION_DIFFICULTIES = ["easy", "medium", "hard"] as const
export type QuestionDifficulty = (typeof QUESTION_DIFFICULTIES)[number]
export const ANSWER_MODES = ["single", "multiple", "written"] as const
export type AnswerMode = (typeof ANSWER_MODES)[number]
export type CodeLanguage = (typeof CODE_LANGUAGES)[number]

export type Question = Schemas["QuestionResponse"]
// Also counts the finished sessions with published grades, which an edit
// never regrades.
export type UpdatedQuestion = Schemas["QuestionUpdateResponse"]

// Not in the schema: the question form sends it as JSON in a multipart field,
// which the backend parses into its QuestionCreate model itself.
export type NewQuestion = {
    prompt: string
    difficulty: QuestionDifficulty
    answer_mode: AnswerMode
    answer_mode_disclosed: boolean
    response_language: CodeLanguage | null
    allow_code_execution: boolean
    code_language: CodeLanguage | null
    code_content: string | null
    choices: Array<{
        id?: number
        label: string
        is_correct: boolean
        // Optional for the backend, which then splits one point across the
        // correct choices (choice_points); the question form always sends it.
        points?: number | null
        /** Position of this choice's new image among the files sent. */
        image_file?: number | null
        remove_image?: boolean
        code_language: CodeLanguage | null
        code_content: string | null
    }>
}

export type QuestionUpdate = NewQuestion & {
    remove_image: boolean
}

export type Quiz = Schemas["QuizResponse"]
export type NewQuiz = Schemas["QuizCreate"]

/** A browser event a student's quiz reports to the teacher. */
export type ReportedViolationType =
    Schemas["StudentQuizViolation"]["event_type"]

export type QuizParticipant = Schemas["QuizParticipantResponse"]
export type QuizAnswerReview = Schemas["QuizAnswerReview"]
// Until the grades are published, and unless the quiz shows a provisional
// correction, the answers carry no expected answers, score, correctness or
// feedback: only the student's own answer.
export type StudentQuizHistoryItem = Schemas["StudentQuizHistoryItem"]
export type QuizSession = Schemas["QuizSessionResponse"]

export type MakeupSession = Schemas["MakeupSessionResponse"]
export type MakeupJoin = Schemas["MakeupSessionJoinResponse"]

export type TrainingHistoryItem = Schemas["TrainingHistoryItem"]

export type StudentQuizQuestion = v.InferOutput<
    typeof StudentQuizQuestionSchema
>
export type StudentQuizSession = v.InferOutput<typeof StudentQuizSessionSchema>
export type StudentAnswerSummary = v.InferOutput<
    typeof StudentAnswerSummarySchema
>
export type TrainingFeedback = v.InferOutput<typeof TrainingFeedbackSchema>
export type StudentQuizJoin = v.InferOutput<typeof StudentQuizJoinSchema>
export type TwoFactorChallenge = v.InferOutput<typeof TwoFactorChallengeSchema>

// The question on screen goes with the answer: the server refuses an answer
// for another one.
export type StudentQuizAnswer = Schemas["StudentQuizAnswer"]
export type StudentQuizAnswerSave = Schemas["StudentQuizAnswerSave"]

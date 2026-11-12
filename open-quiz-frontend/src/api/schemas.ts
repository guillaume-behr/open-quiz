import * as v from "valibot"

import { ANSWER_MODES, QUESTION_DIFFICULTIES } from "./types"

// Runtime schemas of the responses the interface cannot work without: the
// authentication responses, the student's quiz state and the envelope of the
// live updates. Each mirrors its model in open-quiz-backend/app/schemas.py,
// and the TypeScript types in ./types are derived from them. A field the
// backend model gives a default keeps that default here.

export const CODE_LANGUAGES = [
    "javascript",
    "typescript",
    "python",
    "java",
    "csharp",
    "cpp",
    "markup",
    "css",
    "sql",
    "bash",
    "json",
] as const

const SESSION_STATUSES = [
    "waiting",
    "in_progress",
    "paused",
    "finished",
    "cancelled",
] as const

const codeLanguage = v.nullable(v.picklist(CODE_LANGUAGES))

/** `TokenResponse`: the session tokens of a staff login or renewal. */
export const TokenResponseSchema = v.object({
    access_token: v.string(),
    refresh_proof: v.string(),
})

/** `LoginResponse`: the next two-factor step of a staff login. */
export const TwoFactorChallengeSchema = v.object({
    status: v.picklist(["setup_required", "verification_required"]),
    challenge_token: v.string(),
    secret: v.optional(v.nullable(v.string()), null),
    provisioning_uri: v.optional(v.nullable(v.string()), null),
})

/** `LoginResponse | LoginSessionResponse`, told apart by their status. */
export const LoginResponseSchema = v.variant("status", [
    TwoFactorChallengeSchema,
    v.object({
        ...TokenResponseSchema.entries,
        status: v.literal("authenticated"),
    }),
])

/** `UserResponse`: the signed-in staff member. */
export const UserSchema = v.object({
    id: v.number(),
    username: v.string(),
    display_name: v.string(),
    is_admin: v.boolean(),
    is_active: v.boolean(),
    created_at: v.string(),
})

const StudentQuizChoiceSchema = v.object({
    // An opaque token of this participation, never the choice's real id.
    id: v.string(),
    label: v.string(),
    position: v.number(),
    has_image: v.boolean(),
    code_language: codeLanguage,
    code_content: v.nullable(v.string()),
})

export const StudentQuizQuestionSchema = v.object({
    id: v.number(),
    prompt: v.string(),
    difficulty: v.picklist(QUESTION_DIFFICULTIES),
    answer_mode: v.picklist(ANSWER_MODES),
    answer_mode_disclosed: v.boolean(),
    response_language: codeLanguage,
    allow_code_execution: v.boolean(),
    has_image: v.boolean(),
    code_language: codeLanguage,
    code_content: v.nullable(v.string()),
    choices: v.array(StudentQuizChoiceSchema),
    // The most this question is worth; sent in exam mode only.
    total_points: v.optional(v.nullable(v.number()), null),
})

export const StudentAnswerSummarySchema = v.object({
    question_number: v.number(),
    question_id: v.number(),
    prompt: v.string(),
    answer_mode: v.picklist(ANSWER_MODES),
    submitted_answers: v.array(v.string()),
})

export const TrainingFeedbackSchema = v.object({
    question_id: v.number(),
    is_correct: v.nullable(v.boolean()),
    correct_choice_ids: v.array(v.string()),
    expected_answer: v.optional(v.nullable(v.string()), null),
    submitted_answer: v.optional(v.nullable(v.string()), null),
    requires_manual_review: v.optional(v.boolean(), false),
})

/** `StudentQuizStateResponse`: what a student sees of their quiz. */
export const StudentQuizSessionSchema = v.object({
    quiz_title: v.string(),
    source_language: v.string(),
    class_name: v.string(),
    student_name: v.string(),
    join_code: v.string(),
    status: v.picklist(SESSION_STATUSES),
    ends_at: v.nullable(v.string()),
    // The server's time when this state was built (QuizTimer). The backend
    // always sends it; without it the countdown keeps the computer's clock
    // (serverClockAnchor), as it did before this field existed.
    server_now: v.optional(v.string()),
    question_number: v.nullable(v.number()),
    total_questions: v.number(),
    has_answered: v.boolean(),
    answered_count: v.number(),
    allow_previous_questions: v.boolean(),
    allow_answer_review: v.optional(v.boolean(), false),
    awaiting_final_submission: v.optional(v.boolean(), false),
    answer_summaries: v.optional(v.array(StudentAnswerSummarySchema), []),
    accessible_question_numbers: v.optional(v.array(v.number()), []),
    selected_choice_ids: v.optional(v.nullable(v.array(v.string())), null),
    written_answer: v.optional(v.nullable(v.string()), null),
    question: v.nullable(StudentQuizQuestionSchema),
    training_feedback: v.optional(v.nullable(TrainingFeedbackSchema), null),
    potential_score: v.optional(v.nullable(v.number()), null),
    potential_maximum_score: v.optional(v.nullable(v.number()), null),
    pending_manual_review_count: v.optional(v.number(), 0),
})

/** `StudentQuizJoinResponse`: the state, and the participation's token. */
export const StudentQuizJoinSchema = v.object({
    ...StudentQuizSessionSchema.entries,
    participant_token: v.string(),
})

/**
 * Every message of a live feed (app/routers/live.py): a heartbeat, the
 * deletion of the watched session, or a new state of what it watches.
 */
export const LiveMessageSchema = v.variant("type", [
    v.object({ type: v.literal("ping") }),
    v.object({ type: v.literal("deleted") }),
    v.object({
        type: v.picklist(["session", "active_sessions", "makeup_sessions"]),
        data: v.unknown(),
    }),
])

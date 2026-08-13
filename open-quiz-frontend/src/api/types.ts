export type User = {
    id: number
    username: string
    display_name: string
    is_admin: boolean
    is_active: boolean
    created_at: string
}

export type Page<T> = {
    items: T[]
    page: number
    pageSize: number
    total: number
    totalPages: number
}

export type NewUser = {
    username: string
    display_name: string
    password: string
}

export type ProblemReport = {
    id: number
    message: string
    page_path: string
    created_at: string
}

type Student = {
    id: number
    class_id: number
    account_id: number | null
    identifier: string
    display_name: string
    created_at: string
}

export type StudentAccount = {
    id: number
    identifier: string
    display_name: string
    is_active: boolean
    class_id: number | null
    class_name: string | null
    grade_level: string | null
    created_at: string
}

export type CreatedStudentAccount = StudentAccount & {
    generated_password: string
}

export type StudentCredential = {
    identifier: string
    display_name: string
    password: string | null
}

export type StudentClass = {
    id: number
    name: string
    grade_level: string
    student_count: number
    completed_quiz_count: number
    latest_quiz_title: string | null
    latest_quiz_at: string | null
    students: Student[]
    created_at: string
}

export type GradeLevel = {
    id: number
    name: string
}

export type QuestionBank = {
    id: number
    grade_level: string
    chapter: string
    created_at: string
    question_count: number
    easy_question_count: number
    medium_question_count: number
    hard_question_count: number
    training_question_count?: number | null
}

export type NewQuestionBank = {
    grade_level: string
    chapter: string
}

export type QuestionBankImportResult = {
    question_bank: QuestionBank
    questions: Question[]
}

export const QUESTION_DIFFICULTIES = ["easy", "medium", "hard"] as const
export type QuestionDifficulty = (typeof QUESTION_DIFFICULTIES)[number]
export const ANSWER_MODES = ["single", "multiple", "written"] as const
export type AnswerMode = (typeof ANSWER_MODES)[number]
export type CodeLanguage =
    | "javascript"
    | "typescript"
    | "python"
    | "java"
    | "csharp"
    | "cpp"
    | "markup"
    | "css"
    | "sql"
    | "bash"
    | "json"

type QuestionChoice = {
    id: number
    label: string
    is_correct: boolean
    points: number
    position: number
    has_image: boolean
    code_language: CodeLanguage | null
    code_content: string | null
}

export type EncodedImage = {
    content_type: "image/jpeg" | "image/png" | "image/webp" | "image/gif"
    data_base64: string
}

export type Question = {
    id: number
    question_bank_id: number
    prompt: string
    difficulty: QuestionDifficulty
    answer_mode: AnswerMode
    answer_mode_disclosed: boolean
    response_language: CodeLanguage | null
    allow_code_execution: boolean
    has_image: boolean
    code_language: CodeLanguage | null
    code_content: string | null
    choices: QuestionChoice[]
    created_at: string
}

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
        points: number
        image?: EncodedImage | null
        remove_image?: boolean
        code_language: CodeLanguage | null
        code_content: string | null
    }>
}

export type QuestionUpdate = NewQuestion & {
    remove_image: boolean
}

export type Quiz = {
    id: number
    mode: "exam" | "training"
    title: string
    source_language: string
    question_count: number
    duration_seconds: number
    allow_previous_questions: boolean
    allow_negative_points: boolean
    same_questions_for_all: boolean
    easy_question_count: number
    medium_question_count: number
    hard_question_count: number
    question_banks: Array<{
        id: number
        grade_level: string
        chapter: string
        question_count: number
        easy_question_count: number
        medium_question_count: number
        hard_question_count: number
    }>
    created_at: string
}

export type NewQuiz = {
    mode: "exam"
    title: string
    source_language: string
    question_bank_ids: number[]
    duration_seconds: number
    allow_previous_questions: boolean
    allow_negative_points: boolean
    same_questions_for_all: boolean
    easy_question_count: number
    medium_question_count: number
    hard_question_count: number
}

export type QuizParticipant = {
    id: number
    student_identifier: string
    student_display_name: string | null
    answered_count: number
    score: number
    maximum_score: number
    pending_manual_grading_count: number
    violation_count: number
    last_violation_type: string | null
    last_violation_at: string | null
    joined_at: string
}

export type QuizAnswerReview = {
    id: number
    question_id: number
    position: number
    prompt: string
    difficulty: QuestionDifficulty
    answer_mode: AnswerMode
    submitted_answers: string[]
    expected_answers: string[]
    score: number
    max_score: number
    is_graded: boolean
    is_correct: boolean | null
}

type StudentQuizHistoryAnswer = Omit<
    QuizAnswerReview,
    "id" | "score" | "max_score" | "is_graded" | "is_correct"
> & { is_correct: boolean | null }

export type StudentQuizHistoryItem = {
    session_id: number
    quiz_title: string
    class_name: string
    started_at: string
    score: number | null
    maximum_score: number | null
    answers: StudentQuizHistoryAnswer[]
}

export type QuizSession = {
    id: number
    quiz_id: number
    quiz_title: string
    class_id: number | null
    class_name: string
    join_code: string
    status: "waiting" | "in_progress" | "paused" | "finished" | "cancelled"
    participant_count: number
    participants: QuizParticipant[]
    median_maximum_score: number
    current_question_number: number | null
    total_questions: number
    current_submission_count: number
    created_at: string
    started_at: string | null
    ends_at: string | null
    grades_published_at: string | null
}

type MakeupQuizOption = {
    id: number
    title: string
    duration_seconds: number
}

export type MakeupSession = {
    id: number
    class_id: number | null
    class_name: string
    join_code: string
    status: "waiting" | "in_progress" | "paused" | "finished" | "cancelled"
    quizzes: MakeupQuizOption[]
    participant_count: number
    created_at: string
}

export type MakeupJoin = {
    join_code: string
    class_name: string
    status: "waiting"
    quizzes: MakeupQuizOption[]
}

type StudentQuizChoice = {
    id: number
    label: string
    position: number
    has_image: boolean
    code_language: CodeLanguage | null
    code_content: string | null
}

export type StudentQuizQuestion = {
    id: number
    prompt: string
    difficulty: QuestionDifficulty
    answer_mode: AnswerMode
    answer_mode_disclosed: boolean
    response_language: CodeLanguage | null
    allow_code_execution: boolean
    has_image: boolean
    code_language: CodeLanguage | null
    code_content: string | null
    choices: StudentQuizChoice[]
}

export type StudentQuizSession = {
    quiz_title: string
    source_language: string
    class_name: string
    student_name: string
    join_code: string
    status: "waiting" | "in_progress" | "paused" | "finished" | "cancelled"
    ends_at: string | null
    question_number: number | null
    total_questions: number
    has_answered: boolean
    answered_count: number
    allow_previous_questions: boolean
    accessible_question_numbers: number[]
    selected_choice_ids: number[] | null
    written_answer: string | null
    question: StudentQuizQuestion | null
    training_feedback: TrainingFeedback | null
    potential_score: number | null
    potential_maximum_score: number | null
    pending_manual_review_count: number
}

export type TrainingFeedback = {
    question_id: number
    is_correct: boolean | null
    correct_choice_ids: number[]
    expected_answer: string | null
    submitted_answer: string | null
    requires_manual_review: boolean
}

export type TrainingHistoryItem = {
    session_id: number
    question_bank_id: number
    started_at: string
    score: number
    maximum_score: number
    pending_manual_review_count: number
}

export type StudentQuizJoin = StudentQuizSession & {
    participant_token: string
}

export type StudentQuizAnswer = {
    selected_choice_ids?: number[]
    written_answer?: string
}

export type TwoFactorChallenge = {
    status: "setup_required" | "verification_required"
    challenge_token: string
    secret: string | null
    provisioning_uri: string | null
}

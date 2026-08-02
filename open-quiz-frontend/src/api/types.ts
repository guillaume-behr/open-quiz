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

export type Student = {
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
    created_at: string
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
}

export type NewQuestionBank = {
    grade_level: string
    chapter: string
}

export type QuestionBankImportResult = {
    question_bank: QuestionBank
    questions: Question[]
}

export type QuestionDifficulty = "easy" | "medium" | "hard"
export type AnswerMode = "single" | "multiple" | "written"
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

export type QuestionChoice = {
    id: number
    label: string
    is_correct: boolean
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
    code_language: CodeLanguage | null
    code_content: string | null
    choices: Array<{
        id?: number
        label: string
        is_correct: boolean
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
    same_questions_for_all: boolean
    easy_question_count: number
    medium_question_count: number
    hard_question_count: number
    easy_points: number
    medium_points: number
    hard_points: number
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
    same_questions_for_all: boolean
    easy_question_count: number
    medium_question_count: number
    hard_question_count: number
    easy_points: number
    medium_points: number
    hard_points: number
}

export type QuizParticipant = {
    id: number
    student_identifier: string
    student_display_name: string | null
    answered_count: number
    score: number
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
    current_question_number: number | null
    total_questions: number
    current_submission_count: number
    created_at: string
    started_at: string | null
    ends_at: string | null
}

export type StudentQuizChoice = {
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
    selected_choice_ids: number[] | null
    written_answer: string | null
    question: StudentQuizQuestion | null
    training_feedback: TrainingFeedback | null
}

export type TrainingFeedback = {
    question_id: number
    is_correct: boolean
    correct_choice_ids: number[]
    expected_answer: string | null
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

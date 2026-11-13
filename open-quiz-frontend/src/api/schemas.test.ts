import * as v from "valibot"
import { describe, expect, it } from "vitest"

import { ApiError, parseResponse, UNEXPECTED_RESPONSE_CODE } from "./client"
import { StudentQuizJoinSchema, StudentQuizSessionSchema } from "./schemas"

// A state as StudentQuizStateResponse serializes it, defaults left out.
const state = {
    quiz_title: "Science review",
    source_language: "en",
    class_name: "Class 8B",
    student_name: "Alex Example",
    join_code: "ABCD",
    status: "in_progress",
    ends_at: null,
    server_now: "2026-01-01T00:00:00Z",
    question_number: 1,
    total_questions: 3,
    has_answered: false,
    answered_count: 0,
    allow_previous_questions: false,
    question: {
        id: 42,
        prompt: "Pick one",
        difficulty: "easy",
        answer_mode: "single",
        answer_mode_disclosed: true,
        response_language: null,
        allow_code_execution: false,
        has_image: false,
        code_language: "python",
        code_content: "print(1)",
        choices: [
            {
                id: "token-1",
                label: "One",
                position: 0,
                has_image: false,
                code_language: null,
                code_content: null,
            },
        ],
    },
}

describe("student quiz state schema", () => {
    it("fills the fields the backend model gives a default", () => {
        const parsed = v.parse(StudentQuizSessionSchema, state)

        expect(parsed).toMatchObject({
            allow_answer_review: false,
            awaiting_final_submission: false,
            answer_summaries: [],
            accessible_question_numbers: [],
            answered_question_numbers: [],
            skipped_question_numbers: [],
            selected_choice_ids: null,
            written_answer: null,
            training_feedback: null,
            potential_score: null,
            potential_maximum_score: null,
            pending_manual_review_count: 0,
        })
        expect(parsed.question?.total_points).toBeNull()
    })

    it("needs the participant token of a join", () => {
        expect(v.is(StudentQuizJoinSchema, state)).toBe(false)
        expect(
            v.parse(StudentQuizJoinSchema, {
                ...state,
                participant_token: "participant",
            }).participant_token
        ).toBe("participant")
    })

    it.each([
        ["an unknown status", { ...state, status: "archived" }],
        ["a missing question", { ...state, question: undefined }],
        [
            "an unknown code language",
            { ...state, question: { ...state.question, code_language: "go" } },
        ],
    ])("turns %s into an unexpected response error", (_, body) => {
        let error: unknown
        try {
            parseResponse(StudentQuizSessionSchema, body, 201)
        } catch (caught) {
            error = caught
        }
        expect(error).toBeInstanceOf(ApiError)
        expect(error).toMatchObject({
            status: 201,
            code: UNEXPECTED_RESPONSE_CODE,
        })
    })
})

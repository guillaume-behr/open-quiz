import { expect, test } from "@playwright/test"

const student = {
    id: 7,
    identifier: "alex-8b",
    display_name: "Alex Example",
    is_active: true,
    class_id: 2,
    class_name: "Class 8B",
    created_at: "2026-01-01T00:00:00Z",
}

test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
    })
})

test("the root redirects to the student login", async ({ page }) => {
    await page.goto("/")

    await expect(page).toHaveURL(/\/student\/login$/)

    await expect(
        page.getByRole("heading", { name: "Student space" })
    ).toBeVisible()
    await expect(page.getByLabel("Student ID")).toBeVisible()
    await expect(page.getByLabel("Password")).toBeVisible()
    await expect(page.getByRole("button", { name: "Sign in" })).toBeEnabled()
})

test("a signed-in student enters exam mode from the dashboard", async ({
    page,
}) => {
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            json: { access_token: "student-token", student },
        })
    })
    await page.goto("/student/login")
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password").fill("student-password")
    await page.getByRole("button", { name: "Sign in" }).click()

    await expect(page).toHaveURL(/\/student\/dashboard$/)
    await expect(
        page.getByRole("heading", { name: "Welcome, Alex Example" })
    ).toBeVisible()
    await page.getByRole("button", { name: /Enter an exam/ }).click()

    await expect(page).toHaveURL(/\/student\/exam$/)
    await expect(
        page.getByRole("heading", { name: "Join a quiz" })
    ).toBeVisible()
    await expect(page.getByLabel("Quiz code")).toBeVisible()
})

test("a student launches training and sees the correct answer", async ({
    page,
}) => {
    await page.route("**/api/student-auth/login", async (route) => {
        await route.fulfill({
            json: { access_token: "student-token", student },
        })
    })
    await page.route("**/api/quizzes/training", async (route) => {
        await route.fulfill({
            json: [
                {
                    id: 12,
                    mode: "training",
                    title: "Practice science",
                    source_language: "en",
                    question_count: 1,
                    duration_seconds: 1800,
                    allow_previous_questions: false,
                    same_questions_for_all: false,
                    easy_question_count: 1,
                    medium_question_count: 0,
                    hard_question_count: 0,
                    easy_points: 0,
                    medium_points: 0,
                    hard_points: 0,
                    question_banks: [],
                    created_at: "2026-01-01T00:00:00Z",
                },
            ],
        })
    })
    const question = {
        id: 41,
        prompt: "Which planet is red?",
        difficulty: "easy",
        answer_mode: "single",
        answer_mode_disclosed: true,
        response_language: null,
        has_image: false,
        code_language: null,
        code_content: null,
        choices: [
            {
                id: 101,
                label: "Mars",
                position: 0,
                has_image: false,
                code_language: null,
                code_content: null,
            },
            {
                id: 102,
                label: "Venus",
                position: 1,
                has_image: false,
                code_language: null,
                code_content: null,
            },
        ],
    }
    const session = {
        quiz_title: "Practice science",
        source_language: "en",
        class_name: "Class 8B",
        student_name: "Alex Example",
        join_code: "TRAIN1",
        status: "in_progress",
        ends_at: null,
        question_number: 1,
        total_questions: 1,
        has_answered: false,
        answered_count: 0,
        allow_previous_questions: false,
        selected_choice_ids: null,
        written_answer: null,
        question,
        training_feedback: null,
    }
    await page.route("**/api/quizzes/training/12/start", async (route) => {
        await route.fulfill({
            json: { ...session, participant_token: "training-token" },
        })
    })
    await page.route(
        "**/api/quizzes/student/sessions/TRAIN1/answer",
        async (route) => {
            expect(route.request().postDataJSON()).toEqual({
                selected_choice_ids: [101],
            })
            await route.fulfill({
                json: {
                    ...session,
                    status: "finished",
                    question: null,
                    answered_count: 1,
                    training_feedback: {
                        question_id: 41,
                        is_correct: true,
                        correct_choice_ids: [101],
                        expected_answer: null,
                    },
                },
            })
        }
    )

    await page.goto("/student/login")
    await page.getByLabel("Student ID").fill("alex-8b")
    await page.getByLabel("Password").fill("student-password")
    await page.getByRole("button", { name: "Sign in" }).click()
    await page.getByRole("tab", { name: "Training" }).click()
    await expect(page.getByText("Practice science")).toBeVisible()
    await page.getByRole("button", { name: "Start training" }).click()
    await expect(page).toHaveURL(/\/student\/training$/)
    await page.getByLabel("Mars").check()
    await page.getByRole("button", { name: "Submit my answer" }).click()

    await expect(
        page.getByRole("heading", { name: "Correct answer" })
    ).toBeVisible()
    await expect(page.getByText("Mars", { exact: true })).toBeVisible()
    await expect(page.getByText(/score/i)).toHaveCount(0)
})

test("teacher area navigation works without a page reload", async ({
    page,
}) => {
    await page.goto("/student/login")
    await page.getByRole("link", { name: "Teacher area" }).click()

    await expect(page).toHaveURL(/\/teacher\/login$/)
    await expect(page.getByRole("link", { name: "Home" })).toBeVisible()
    await expect(page.getByRole("heading").first()).toBeVisible()
})

test("student login remains usable on a mobile viewport", async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 667 })
    await page.goto("/student/login")

    const loginButton = page.getByRole("button", { name: "Sign in" })
    await expect(loginButton).toBeInViewport()
    await expect(page.getByLabel("Student ID")).toBeEditable()
    await expect(page.getByLabel("Password")).toBeEditable()
})

import { expect, test } from "./fixtures"
import { mockTeacherApi } from "./teacher-api"

test("teacher creates, exports, imports, and deletes question banks", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()

    await page.getByRole("button", { name: "New question bank" }).click()
    const createDialog = page.getByRole("dialog", {
        name: "New question bank",
    })
    await createDialog.getByLabel("Grade level").selectOption("Grade 8")
    await createDialog.getByLabel("Question bank title").fill("Thermodynamics")
    await createDialog.getByRole("button", { name: "Create" }).click()
    await expect(page.getByText("Thermodynamics")).toBeVisible()
    expect(
        requests
            .find(
                (request) =>
                    new URL(request.url()).pathname === "/api/question-banks" &&
                    request.method() === "POST"
            )
            ?.postDataJSON()
    ).toEqual({ grade_level: "Grade 8", chapter: "Thermodynamics" })

    const existingBank = page.getByRole("listitem").filter({
        hasText: "Matter and energy",
    })
    const exportPromise = page.waitForEvent("download")
    await existingBank.getByRole("button", { name: "Export" }).click()
    expect((await exportPromise).suggestedFilename()).toBe(
        "question-bank-grade-8-matter-and-energy.json"
    )

    const examplePromise = page.waitForEvent("download")
    await page.getByRole("button", { name: "Download example" }).click()
    expect((await examplePromise).suggestedFilename()).toBe(
        "open-quiz-questions-example.json"
    )

    await page.getByRole("button", { name: "Import" }).click()
    const importDialog = page.getByRole("dialog", {
        name: "Import a question bank",
    })
    await importDialog.getByLabel(".json file").setInputFiles({
        name: "mechanics.json",
        mimeType: "application/json",
        buffer: Buffer.from('{"grade_level":"Grade 10"}'),
    })
    await importDialog.getByRole("button", { name: "Import" }).click()
    await expect(page.getByText("Imported mechanics")).toBeVisible()
    await expect(page.getByRole("status")).toHaveText(
        "New question bank created with 1 question."
    )

    // A bank quizzes draw from warns that they lose it; a new one does not.
    const quizWarning = /a quiz that draws only from it needs another bank/
    await existingBank
        .getByRole("button", { name: "Delete question bank" })
        .click()
    const deleteDialog = page.getByRole("dialog", {
        name: "Delete question bank",
    })
    await expect(deleteDialog).toContainText(quizWarning)
    await deleteDialog.getByRole("button", { name: "Cancel" }).click()
    await expect(deleteDialog).toHaveCount(0)

    const createdBank = page.getByRole("listitem").filter({
        hasText: "Thermodynamics",
    })
    await createdBank
        .getByRole("button", { name: "Delete question bank" })
        .click()
    await expect(deleteDialog).not.toContainText(quizWarning)
    await deleteDialog
        .getByRole("button", { name: "Delete question bank" })
        .click()
    await expect(page.getByText("Thermodynamics")).toHaveCount(0)
})

test("teacher creates, edits, and deletes a scored question", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()

    const bankCard = page.getByRole("listitem").filter({
        hasText: "Matter and energy",
    })
    await bankCard.getByRole("button", { name: "Edit question bank" }).click()
    const questionsDialog = page.getByRole("dialog", {
        name: "Edit question bank",
    })
    const questionFilters = questionsDialog.getByRole("button", {
        name: /Filters/,
    })
    await expect(questionFilters).toHaveAttribute("aria-expanded", "false")
    await expect(questionsDialog.getByLabel("Minimum points")).toBeHidden()
    await questionFilters.click()
    await expect(questionFilters).toHaveAttribute("aria-expanded", "true")
    await expect(questionsDialog.getByLabel("Minimum points")).toBeVisible()
    await questionFilters.click()
    await expect(questionFilters).toHaveAttribute("aria-expanded", "false")
    await expect(questionsDialog.getByLabel("Minimum points")).toBeHidden()
    await questionsDialog
        .getByRole("button", { name: "Add a question" })
        .click()

    const addDialog = page.getByRole("dialog", { name: "Add a question" })
    await addDialog
        .getByLabel("Question")
        .fill("Which form of energy is stored?")
    await addDialog.getByLabel("Difficulty").selectOption("hard")
    await addDialog.getByPlaceholder("Choice 1").fill("Potential energy")
    await addDialog.getByPlaceholder("Choice 2").fill("Sound energy")
    await addDialog.getByLabel("Points for choice 1").fill("4")
    await addDialog.getByLabel("Points for choice 2").fill("-1")
    await addDialog.getByRole("button", { name: "Save question" }).click()

    await expect(
        questionsDialog.getByText("1. Which form of energy is stored?")
    ).toBeVisible()
    await expect(
        questionsDialog.locator("ol").getByText("Hard", { exact: true })
    ).toBeVisible()
    const createRequest = requests.find(
        (request) =>
            new URL(request.url()).pathname ===
                "/api/question-banks/21/questions" &&
            request.method() === "POST"
    )
    expect(createRequest?.postData()).toContain(
        "Which form of energy is stored?"
    )
    expect(createRequest?.postData()).toContain("Potential energy")
    expect(createRequest?.postData()).toContain('"points":4')
    expect(createRequest?.postData()).toContain('"points":-1')

    await questionsDialog.getByRole("button", { name: "Edit" }).click()
    const editDialog = page.getByRole("dialog", { name: "Edit question" })
    await editDialog
        .getByLabel("Question")
        .fill("Which kind of energy is stored?")
    await editDialog.getByRole("button", { name: "Save changes" }).click()
    await expect(
        questionsDialog.getByText("1. Which kind of energy is stored?")
    ).toBeVisible()
    await expect(
        questionsDialog.getByRole("status").filter({
            hasText:
                "The grades already published for 2 sessions were left unchanged.",
        })
    ).toBeVisible()

    await questionsDialog
        .getByRole("button", { name: "Delete question" })
        .click()
    const deleteDialog = page.getByRole("dialog", {
        name: "Delete question",
    })
    await deleteDialog.getByRole("button", { name: "Delete question" }).click()
    await expect(
        questionsDialog.getByText("No questions in this question bank.")
    ).toBeVisible()
})

test("question bank import identifies JSON syntax and validation locations", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()
    await page.getByRole("button", { name: "Import" }).click()

    const dialog = page.getByRole("dialog", {
        name: "Import a question bank",
    })
    const fileInput = dialog.getByLabel(".json file")
    await fileInput.setInputFiles({
        name: "invalid.json",
        mimeType: "application/json",
        buffer: Buffer.from('{\n  "version": 1,\n  "questions": [}\n'),
    })
    await dialog.getByRole("button", { name: "Import" }).click()
    await expect(dialog.getByRole("alert")).toContainText(
        /JSON — line 3, column \d+:/
    )

    await page.route("**/api/question-banks/import", async (route) => {
        await route.fulfill({
            status: 422,
            json: {
                detail: [
                    {
                        type: "string_too_short",
                        loc: ["body", "questions", 1, "choices", 0, "label"],
                        msg: "String should have at least 1 character",
                    },
                ],
            },
        })
    })
    await fileInput.setInputFiles({
        name: "invalid-bank.json",
        mimeType: "application/json",
        buffer: Buffer.from(
            JSON.stringify({
                version: 1,
                question_bank: {
                    grade_level: "Grade 8",
                    chapter: "Invalid bank",
                },
                questions: [],
            })
        ),
    })
    await dialog.getByRole("button", { name: "Import" }).click()
    await expect(dialog.getByRole("alert")).toContainText(
        "$.questions[1].choices[0].label: String should have at least 1 character"
    )
})

test("Enter in a question filter keeps the question-bank dialog open", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()
    await page
        .getByRole("listitem")
        .filter({ hasText: "Matter and energy" })
        .getByRole("button", { name: "Edit question bank" })
        .click()
    const dialog = page.getByRole("dialog", { name: "Edit question bank" })
    await dialog.getByRole("button", { name: /Filters/ }).click()
    await dialog.getByLabel("Minimum points").fill("1")
    await dialog.getByLabel("Minimum points").press("Enter")

    await expect(dialog.getByLabel("Minimum points")).toBeFocused()
    await expect(dialog).toBeVisible()
    expect(
        requests.filter(
            (request) =>
                request.method() !== "GET" &&
                /^\/api\/question-banks\/21(\/update)?$/.test(
                    new URL(request.url()).pathname
                )
        )
    ).toEqual([])
})

test("editing a question returns to the same place in the question list", async ({
    page,
}) => {
    await mockTeacherApi(page)
    let questions = Array.from({ length: 30 }, (_, index) => ({
        id: 100 + index,
        question_bank_id: 21,
        prompt: `Question number ${index + 1}`,
        points: 1,
        difficulty: "easy",
        answer_mode: "single",
        answer_mode_disclosed: true,
        response_language: null,
        has_image: false,
        code_language: null,
        code_content: null,
        choices: [
            {
                id: 1000 + index,
                label: "Answer",
                is_correct: true,
                points: 1,
                position: 0,
                has_image: false,
                code_language: null,
                code_content: null,
            },
        ],
        created_at: "2026-01-06T12:00:00Z",
    }))
    await page.route(
        "http://127.0.0.1:4173/api/question-banks/21/questions",
        (route) => route.fulfill({ json: questions })
    )
    await page.route(
        /\/api\/question-banks\/questions\/\d+\/update$/,
        (route) => {
            const id = Number(
                new URL(route.request().url()).pathname.split("/")[4]
            )
            questions = questions.map((question) =>
                question.id === id
                    ? { ...question, prompt: "Edited question" }
                    : question
            )
            return route.fulfill({
                json: {
                    ...questions.find((question) => question.id === id),
                    published_sessions_not_regraded: 0,
                },
            })
        }
    )
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()
    await page
        .getByRole("listitem")
        .filter({ hasText: "Matter and energy" })
        .getByRole("button", { name: "Edit question bank" })
        .click()
    const bankDialog = page.getByRole("dialog", { name: "Edit question bank" })
    await bankDialog.getByRole("button", { name: /Filters/ }).click()
    await bankDialog.getByLabel("Sort questions").selectOption("default")
    const list = bankDialog.getByRole("list").filter({
        hasText: "Question number 1",
    })
    const dialogBody = bankDialog.locator("[data-dialog-body]")
    await expect(list.getByText("Question number 30")).toBeAttached()
    await dialogBody.evaluate((element) => {
        element.scrollTop = element.scrollHeight
    })
    await list.evaluate((element) => {
        element.scrollTop = element.scrollHeight / 2
    })
    // Clicking scrolls the button into view: measure once it is in view.
    const editButton = list
        .getByRole("listitem")
        .filter({ hasText: "Question number 16" })
        .getByRole("button", { name: "Edit", exact: true })
    await editButton.scrollIntoViewIfNeeded()
    const listScrollTop = await list.evaluate((element) => element.scrollTop)
    const dialogScrollTop = await dialogBody.evaluate(
        (element) => element.scrollTop
    )
    expect(listScrollTop).toBeGreaterThan(0)
    expect(dialogScrollTop).toBeGreaterThan(0)

    await editButton.click()
    const formDialog = page.getByRole("dialog", {
        name: "Edit question",
        exact: true,
    })
    await formDialog.getByRole("button", { name: "Save changes" }).click()
    await expect(formDialog).toBeHidden()

    await expect(list.getByText("Edited question")).toBeVisible()
    await expect(bankDialog.getByLabel("Sort questions")).toHaveValue("default")
    expect(await list.evaluate((element) => element.scrollTop)).toBeCloseTo(
        listScrollTop,
        -1
    )
    expect(
        await dialogBody.evaluate((element) => element.scrollTop)
    ).toBeCloseTo(dialogScrollTop, -1)
})

test("switching a question to written and back keeps its correct choice", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()
    await page
        .getByRole("listitem")
        .filter({ hasText: "Matter and energy" })
        .getByRole("button", { name: "Edit question bank" })
        .click()
    await page
        .getByRole("dialog", { name: "Edit question bank" })
        .getByRole("button", { name: "Add a question" })
        .click()
    const dialog = page.getByRole("dialog", { name: "Add a question" })
    await dialog.getByLabel("Question").fill("Which one is a noble gas?")
    await dialog.getByRole("button", { name: "Add a choice" }).click()
    await dialog.getByPlaceholder("Choice 1").fill("Oxygen")
    await dialog.getByPlaceholder("Choice 2").fill("Nitrogen")
    await dialog.getByPlaceholder("Choice 3").fill("Neon")
    await dialog.getByLabel("Choice 3 is correct").check()

    await dialog
        .getByLabel("Answer type", { exact: true })
        .selectOption("written")
    await dialog
        .getByLabel("Answer type", { exact: true })
        .selectOption("single")

    await expect(dialog.getByLabel("Choice 3 is correct")).toBeChecked()
    await expect(dialog.getByLabel("Choice 1 is correct")).not.toBeChecked()
    await dialog.getByRole("button", { name: "Save question" }).click()
    await expect(dialog).toBeHidden()
    const createRequest = requests.find(
        (request) =>
            new URL(request.url()).pathname ===
                "/api/question-banks/21/questions" &&
            request.method() === "POST"
    )
    const body = createRequest?.postData() ?? ""
    const payload = JSON.parse(
        body.slice(body.indexOf("{"), body.lastIndexOf("}") + 1)
    ) as { choices: { label: string; is_correct: boolean }[] }
    expect(
        payload.choices.map(({ label, is_correct }) => ({ label, is_correct }))
    ).toEqual([
        { label: "Oxygen", is_correct: false },
        { label: "Nitrogen", is_correct: false },
        { label: "Neon", is_correct: true },
    ])
})

test("a new choice keeps its own code result when an earlier choice is removed", async ({
    page,
}) => {
    await mockTeacherApi(page)
    const savedChoice = {
        is_correct: false,
        points: 0,
        has_image: false,
        code_language: null,
        code_content: null,
    }
    await page.route(
        "http://127.0.0.1:4173/api/question-banks/21/questions",
        (route) =>
            route.fulfill({
                json: [
                    {
                        id: 81,
                        question_bank_id: 21,
                        prompt: "Which unit measures energy?",
                        points: 1,
                        difficulty: "easy",
                        answer_mode: "single",
                        answer_mode_disclosed: true,
                        response_language: null,
                        has_image: false,
                        code_language: null,
                        code_content: null,
                        choices: [
                            {
                                ...savedChoice,
                                id: 1,
                                label: "Joule",
                                is_correct: true,
                                points: 1,
                                position: 0,
                            },
                            {
                                ...savedChoice,
                                id: 2,
                                label: "Metre",
                                position: 1,
                            },
                        ],
                        created_at: "2026-01-06T12:00:00Z",
                    },
                ],
            })
    )
    await page.goto("/teacher/dashboard")
    await page
        .getByRole("button", { name: "Question banks", exact: true })
        .click()
    await page
        .getByRole("listitem")
        .filter({ hasText: "Matter and energy" })
        .getByRole("button", { name: "Edit question bank" })
        .click()
    await page
        .getByRole("dialog", { name: "Edit question bank" })
        .getByRole("button", { name: "Edit" })
        .click()
    const dialog = page.getByRole("dialog", { name: "Edit question" })
    await dialog.getByRole("button", { name: "Add a choice" }).click()
    await dialog.getByPlaceholder("Choice 3").fill("Watt")
    await dialog.getByRole("button", { name: "Add code" }).last().click()
    await dialog.getByLabel("Code language for choice 3").selectOption("python")
    await dialog.getByLabel("Source code").last().fill("print('third')")
    await dialog.getByRole("button", { name: "Run", exact: true }).click()
    await expect(dialog.getByText("third", { exact: true })).toBeVisible({
        timeout: 60_000,
    })

    await dialog.getByLabel("Remove choice 2").click()

    await expect(dialog.getByPlaceholder("Choice 2")).toHaveValue("Watt")
    await expect(dialog.getByLabel("Code language for choice 2")).toHaveValue(
        "python"
    )
    await expect(dialog.getByText("third", { exact: true })).toHaveCount(1)
    await expect(dialog.getByText("third", { exact: true })).toBeVisible()
})

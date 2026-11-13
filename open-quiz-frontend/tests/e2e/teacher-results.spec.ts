import { expect, test } from "./fixtures"
import { mockTeacherApi } from "./teacher-api"

test("teacher reviews, grades, exports, and deletes quiz results", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Results", exact: true }).click()
    await expect(
        page.getByRole("heading", { name: "Results", level: 3 })
    ).toBeVisible()
    await page
        .getByRole("combobox", { name: "Class", exact: true })
        .selectOption({ label: "Grade 8 Class 8B" })
    await expect
        .poll(() =>
            requests.some((request) => {
                const url = new URL(request.url())
                return (
                    url.pathname === "/api/quizzes/sessions/results" &&
                    // The id: a name search would also match "Class 8BX".
                    url.searchParams.get("class_id") === "11" &&
                    !url.searchParams.has("class_search")
                )
            })
        )
        .toBe(true)

    const resultCard = page.getByRole("article").filter({
        hasText: "Science checkpoint",
    })
    await expect(resultCard.getByText("Class 8B")).toBeVisible()
    const resultStatusIcon = resultCard.getByRole("img", {
        name: "Grades not published",
    })
    const resultTitle = resultCard.getByRole("heading", {
        name: "Science checkpoint",
    })
    await expect(resultStatusIcon).toHaveClass(/text-warning/)
    const resultStatusIconBox = await resultStatusIcon.boundingBox()
    const resultTitleBox = await resultTitle.boundingBox()
    expect(resultStatusIconBox).not.toBeNull()
    expect(resultTitleBox).not.toBeNull()
    expect(resultStatusIconBox!.x + resultStatusIconBox!.width).toBeLessThan(
        resultTitleBox!.x
    )
    await page.getByRole("button", { name: "Schedule" }).click()
    await expect(
        page.getByRole("button", { name: "Previous week" })
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Next week" })).toBeVisible()
    await expect(page.getByText(/\d{1,2}:00/).first()).toBeVisible()
    await page
        .getByRole("button", { name: "Grade quiz — Science checkpoint" })
        .click()
    await expect(
        page.getByRole("dialog", { name: "Science checkpoint" })
    ).toBeVisible()
    await page
        .getByRole("dialog", { name: "Science checkpoint" })
        .getByRole("button", { name: "Close" })
        .click()
    await page.getByRole("button", { name: "Cards" }).click()
    await resultCard.getByRole("button", { name: "Grade quiz" }).click()

    const resultDialog = page.getByRole("dialog", {
        name: "Science checkpoint",
    })
    await expect(resultDialog.getByText("Class 8B")).toHaveCount(1)
    await expect(resultDialog.getByText("Alex Example")).toBeVisible()
    await expect(
        resultDialog.getByText("Median available points")
    ).toBeVisible()
    const scoreHeading = resultDialog.getByText("Grade", {
        exact: true,
    })
    const participantRow = resultDialog.locator('[data-participant-id="91"]')
    const participantScore = participantRow.locator("[data-participant-score]")
    await expect(scoreHeading).toBeVisible()
    // Whatever a paper is marked out of, the grade is read on the same scale.
    await expect(participantScore).toContainText(/4\s*\/\s*20/)
    await participantScore.getByText("4 / 20").hover()
    // The tooltip is portalled out of the dialog.
    await expect(
        page.getByRole("tooltip").filter({
            hasText: "Full grade: 2 / 10 points",
        })
    ).toBeVisible()
    await expect
        .poll(() =>
            resultDialog.evaluate((element) =>
                element
                    .getAnimations()
                    .every((animation) => animation.playState === "finished")
            )
        )
        .toBe(true)
    const scoreHeadingBox = await scoreHeading.boundingBox()
    const participantScoreBox = await participantScore.boundingBox()
    expect(scoreHeadingBox).not.toBeNull()
    expect(participantScoreBox).not.toBeNull()
    expect(participantScoreBox!.x).toBeCloseTo(scoreHeadingBox!.x, 0)
    expect(participantScoreBox!.width).toBeCloseTo(scoreHeadingBox!.width, 0)
    const medianGapMessage =
        "This student's available points (10) differ from the group median (5) by at least 3 points. A different question selection may explain the difference."
    const medianGapIndicator = resultDialog.getByRole("button", {
        name: medianGapMessage,
    })
    await expect(medianGapIndicator).toBeVisible()
    const medianGapIndicatorBox = await medianGapIndicator.boundingBox()
    const participantScoreValueBox = await participantScore
        .locator("span")
        .last()
        .boundingBox()
    expect(medianGapIndicatorBox).not.toBeNull()
    expect(participantScoreValueBox).not.toBeNull()
    expect(
        medianGapIndicatorBox!.x + medianGapIndicatorBox!.width
    ).toBeLessThan(participantScoreValueBox!.x)
    await medianGapIndicator.hover()
    await expect(
        page.getByRole("tooltip").getByText(medianGapMessage)
    ).toBeVisible()
    await expect(
        resultDialog.getByText("alex-8b", { exact: true })
    ).toHaveCount(1)
    const pendingGradingIndicator = resultDialog.getByRole("button", {
        name: "1 to grade",
    })
    await expect(pendingGradingIndicator).toBeVisible()
    await expect(participantRow).toHaveClass(/bg-warning\/10/)
    const participantGradingStatus = participantRow.locator(
        '[data-grading-status="pending"]'
    )
    await expect(participantGradingStatus).toHaveClass(/text-warning/)
    await pendingGradingIndicator.hover()
    await expect(
        page.getByRole("tooltip").getByText("1 to grade")
    ).toBeVisible()
    await resultDialog.getByRole("button", { name: "View answers" }).click()

    const answersDialog = page.getByRole("dialog", { name: "Student answers" })
    await expect(
        answersDialog.getByText("Energy moves between systems.")
    ).toBeVisible()
    await answersDialog.getByLabel("Awarded score").fill("3.5")
    await answersDialog.getByRole("button", { name: "Confirm grade" }).click()
    await expect(answersDialog.getByText("3.5 / 5")).toBeVisible()
    // Partial credit is coloured by an inline gradient, not a class: 3.5 out
    // of 5 sits 70% of the way from destructive to success. A solid red here
    // would mean partial credit reads as an outright failure again.
    await expect(
        answersDialog
            .locator("[style]")
            .filter({
                has: page.getByText("Energy moves between systems."),
            })
            .last()
    ).toHaveAttribute("style", /var\(--destructive\) 30%, var\(--success\) 70%/)
    expect(
        requests
            .find((request) =>
                new URL(request.url()).pathname.endsWith("/answers/92/grade")
            )
            ?.postDataJSON()
    ).toEqual({ score: 3.5 })
    await answersDialog.getByRole("button", { name: "Close" }).click()
    await expect(participantRow).not.toHaveClass(/bg-warning\/10/)
    await expect(
        participantRow.locator('[data-grading-status="complete"]')
    ).toHaveClass(/text-success/)
    await expect(
        resultDialog.getByRole("button", { name: "1 to grade" })
    ).toHaveCount(0)
    await expect(medianGapIndicator).toBeVisible()
    await resultDialog.getByRole("button", { name: "Publish grades" }).click()
    await expect(
        resultDialog.getByRole("button", { name: "Grades published" })
    ).toBeDisabled()
    await resultDialog.getByRole("button", { name: "View answers" }).click()
    await expect(answersDialog.getByLabel("Awarded score")).toBeDisabled()
    await expect(
        answersDialog.getByRole("button", { name: "Update score" })
    ).toBeDisabled()
    await answersDialog.getByRole("button", { name: "Close" }).click()
    expect(
        requests.some(
            (request) =>
                new URL(request.url()).pathname ===
                    "/api/quizzes/sessions/90/publish-grades" &&
                request.method() === "POST"
        )
    ).toBe(true)
    await resultDialog.getByRole("button", { name: "Close" }).click()
    await expect(
        resultCard.getByRole("img", { name: "Grades published" })
    ).toHaveClass(/text-success/)

    await page.getByRole("button", { name: "Export results" }).click()
    const exportDialog = page.getByRole("dialog", { name: "Export results" })
    await exportDialog.getByLabel("Quiz title").selectOption("31")
    const downloadPromise = page.waitForEvent("download")
    await exportDialog.getByRole("button", { name: "Export CSV" }).click()
    const download = await downloadPromise
    expect(download.suggestedFilename()).toBe("class-results-11-quiz-31.csv")
    expect(
        requests.some((request) => {
            const url = new URL(request.url())
            return (
                url.pathname === "/api/quizzes/sessions/results/export" &&
                url.searchParams.get("class_id") === "11" &&
                url.searchParams.get("quiz_id") === "31"
            )
        })
    ).toBe(true)

    await resultCard
        .getByRole("button", { name: /^Delete the result of / })
        .click()
    const deleteDialog = page.getByRole("dialog", {
        name: "Delete this result",
    })
    await deleteDialog.getByRole("button", { name: "Delete" }).click()
    await expect(resultCard).toHaveCount(0)
})

test("the results schedule shows every session of its week, not one page", async ({
    page,
}) => {
    await mockTeacherApi(page)
    const weekRequests: URL[] = []
    page.on("request", (request) => {
        const url = new URL(request.url())
        if (url.searchParams.has("started_from")) weekRequests.push(url)
    })
    // Page 1 of the list holds one session; another of the same week sits on
    // a later page and only a request for the week returns both.
    let first: Record<string, unknown> | undefined
    page.on("response", async (response) => {
        const url = new URL(response.url())
        if (
            url.pathname === "/api/quizzes/sessions/results" &&
            !url.searchParams.has("started_from") &&
            !url.searchParams.has("started_before")
        )
            first ??= ((await response.json()) as Record<string, unknown>[])[0]
    })
    await page.route("**/api/quizzes/sessions/results?**", async (route) => {
        const url = new URL(route.request().url())
        if (url.searchParams.has("started_from")) {
            await expect.poll(() => first).toBeDefined()
            const sameWeek = {
                ...first,
                id: 95,
                quiz_title: "Later page checkpoint",
                started_at: "2026-01-07T14:00:00Z",
                ends_at: "2026-01-07T14:30:00Z",
            }
            return route.fulfill({
                json: [sameWeek, first],
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "100",
                    "X-Total-Count": "2",
                },
            })
        }
        if (url.searchParams.has("started_before"))
            return route.fulfill({
                json: [],
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "1",
                    "X-Total-Count": "0",
                },
            })
        return route.fallback()
    })
    await page.goto("/teacher/dashboard?section=results")
    await page.getByRole("button", { name: "Schedule" }).click()

    await expect(
        page.getByRole("button", {
            name: "Grade quiz — Later page checkpoint",
        })
    ).toBeVisible()
    expect(weekRequests).toHaveLength(1)
    const params = weekRequests[0]?.searchParams ?? new URLSearchParams()
    expect(params.get("page_size")).toBe("100")
    // Monday to Monday, whatever the time zone the browser runs in.
    expect(
        new Date(params.get("started_before") ?? "").getTime() -
            new Date(params.get("started_from") ?? "").getTime()
    ).toBe(7 * 24 * 60 * 60 * 1000)
    await expect(
        page.getByRole("button", { name: "Previous week" })
    ).toBeDisabled()
    await expect(page.getByRole("button", { name: "Next week" })).toBeDisabled()
})

test("an empty or out-of-range score is not saved", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard?section=results")
    await page
        .getByRole("article")
        .filter({ hasText: "Science checkpoint" })
        .getByRole("button", { name: "Grade quiz" })
        .click()
    await page
        .getByRole("dialog", { name: "Science checkpoint" })
        .getByRole("button", { name: "View answers" })
        .click()
    const answersDialog = page.getByRole("dialog", { name: "Student answers" })
    const confirm = answersDialog.getByRole("button", { name: "Confirm grade" })

    for (const score of ["", "6"]) {
        await answersDialog.getByLabel("Awarded score").fill(score)
        await confirm.click()
        await expect(answersDialog.getByRole("alert")).toHaveText(
            "Enter a score between 0 and 5."
        )
    }
    expect(
        requests.some((request) =>
            new URL(request.url()).pathname.endsWith("/answers/92/grade")
        )
    ).toBe(false)
})

test("a failed grade says so, not that answers failed to load", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.route("**/answers/92/grade", (route) =>
        route.fulfill({ status: 500, json: {} })
    )
    await page.goto("/teacher/dashboard?section=results")
    await page
        .getByRole("article")
        .filter({ hasText: "Science checkpoint" })
        .getByRole("button", { name: "Grade quiz" })
        .click()
    await page
        .getByRole("dialog", { name: "Science checkpoint" })
        .getByRole("button", { name: "View answers" })
        .click()
    const answersDialog = page.getByRole("dialog", { name: "Student answers" })
    await answersDialog.getByLabel("Awarded score").fill("3")
    await answersDialog.getByRole("button", { name: "Confirm grade" }).click()
    await expect(answersDialog.getByRole("alert")).toHaveText(
        "Unable to save this grade."
    )
})

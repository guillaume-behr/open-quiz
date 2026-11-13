import { expect, test } from "./fixtures"
import { existingClass, mockTeacherApi } from "./teacher-api"

test("teacher can create a class", async ({ page }) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()
    await page.getByRole("button", { name: "New class" }).click()
    const dialog = page.getByRole("dialog", { name: "New class" })
    await dialog.getByRole("combobox", { name: "Class" }).fill("Class 9A")
    await dialog.getByLabel("Grade level").selectOption("Grade 8")
    await dialog.getByRole("button", { name: "New class", exact: true }).click()

    await expect(
        page.getByRole("article").filter({ hasText: "Class 9A" })
    ).toBeVisible()
    const createRequest = requests.find(
        (request) =>
            new URL(request.url()).pathname === "/api/classes" &&
            request.method() === "POST"
    )
    expect(createRequest?.postDataJSON()).toEqual({
        name: "Class 9A",
        grade_level: "Grade 8",
    })
})

test("teacher updates a class and manages student assignments", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()

    const classCard = page.getByRole("article").filter({ hasText: "Class 8B" })
    await classCard.getByRole("button", { name: "Edit class" }).click()
    const editDialog = page.getByRole("dialog", { name: "Edit class" })
    await editDialog
        .getByRole("combobox", { name: "Class", exact: true })
        .fill("Class 8 Advanced")
    await editDialog.getByRole("button", { name: "Save class" }).click()
    await expect(page.getByText("Class 8 Advanced")).toBeVisible()

    const updatedCard = page.getByRole("article").filter({
        hasText: "Class 8 Advanced",
    })
    await updatedCard.getByRole("button", { name: "Edit class" }).click()
    const manageDialog = page.getByRole("dialog", {
        name: "Edit class",
    })
    await manageDialog.getByRole("button", { name: "Assign a student" }).click()
    const assignDialog = page.getByRole("dialog", {
        name: "Assign a student",
    })
    const availableStudent = assignDialog
        .getByRole("button")
        .filter({ hasText: "Dorothy Vaughan" })
    await expect(availableStudent).toContainText("Former class")
    await expect(availableStudent).toContainText("Grade 7")
    await availableStudent.click()
    await assignDialog.getByRole("button", { name: "Assign 1 student" }).click()
    await expect(manageDialog.getByText("Dorothy Vaughan")).toBeVisible()

    await manageDialog
        .getByRole("button", { name: "Remove from class" })
        .click()
    await expect(manageDialog.getByText("Dorothy Vaughan")).toHaveCount(0)
    await manageDialog.getByRole("button", { name: "Close" }).click()

    await updatedCard.getByRole("button", { name: "Delete class" }).click()
    const deleteDialog = page.getByRole("dialog", { name: "Delete class" })
    await deleteDialog.getByRole("button", { name: "Delete" }).click()
    await expect(page.getByText("Class 8 Advanced")).toHaveCount(0)

    expect(
        requests
            .filter((request) =>
                new URL(request.url()).pathname.startsWith("/api/classes/11")
            )
            .map((request) => ({
                method: request.method(),
                path: new URL(request.url()).pathname,
            }))
    ).toEqual([
        { method: "POST", path: "/api/classes/11/update" },
        { method: "POST", path: "/api/classes/11/accounts/43" },
        { method: "DELETE", path: "/api/classes/11/accounts/43" },
        { method: "DELETE", path: "/api/classes/11" },
    ])
})

test("teacher creates, updates, disables, and deletes a student account", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")

    await page.getByRole("button", { name: "New student account" }).click()
    const createDialog = page.getByRole("dialog", {
        name: "New student account",
    })
    await createDialog.getByLabel("First name").fill("Grace")
    await createDialog.getByLabel("Last name").fill("Hopper")
    await createDialog.getByRole("button", { name: "Save student" }).click()

    await expect(page.getByText("hopper-grace", { exact: true })).toBeVisible()
    await expect(page.getByText("Grace Hopper")).toBeVisible()
    expect(
        requests
            .find(
                (request) =>
                    new URL(request.url()).pathname === "/api/students" &&
                    request.method() === "POST"
            )
            ?.postDataJSON()
    ).toEqual({ first_name: "Grace", last_name: "Hopper" })

    const studentCard = page.getByRole("article").filter({
        hasText: "hopper-grace",
    })
    await studentCard.getByRole("button", { name: "Edit student" }).click()
    const editDialog = page.getByRole("dialog", {
        name: "Edit student account",
    })
    await editDialog.getByLabel("Student name").fill("Rear Admiral Hopper")
    await editDialog.getByLabel("Student ID").fill("grace-hopper")
    await editDialog
        .getByLabel("New password (optional)")
        .fill("new-student-password")
    await editDialog.getByLabel("Active account").uncheck()
    await editDialog.getByRole("button", { name: "Save student" }).click()

    await expect(page.getByText("Rear Admiral Hopper")).toBeVisible()
    await expect(page.getByText(/Account disabled/)).toBeVisible()
    expect(
        requests
            .find((request) =>
                new URL(request.url()).pathname.endsWith("/42/update")
            )
            ?.postDataJSON()
    ).toEqual({
        display_name: "Rear Admiral Hopper",
        identifier: "grace-hopper",
        password: "new-student-password",
        is_active: false,
    })

    const updatedCard = page.getByRole("article").filter({
        hasText: "grace-hopper",
    })
    await updatedCard.getByRole("button", { name: "Delete student" }).click()
    const deleteDialog = page.getByRole("dialog", { name: "Delete student" })
    await deleteDialog.getByRole("button", { name: "Delete" }).click()
    await expect(page.getByText("Rear Admiral Hopper")).toHaveCount(0)
    expect(
        requests.some(
            (request) =>
                new URL(request.url()).pathname === "/api/students/42" &&
                request.method() === "DELETE"
        )
    ).toBe(true)
})

test("class list recovers after a temporary load failure", async ({ page }) => {
    await mockTeacherApi(page)
    await page.route(
        /^http:\/\/127\.0\.0\.1:4173\/api\/classes\?/,
        async (route) => {
            const search = new URL(route.request().url()).searchParams.get(
                "search"
            )
            if (search === "first request") {
                await route.fulfill({ status: 503, body: "{}" })
                return
            }
            await route.fallback()
        }
    )
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()
    await expect(
        page.getByRole("article").filter({ hasText: "Class 8B" })
    ).toBeVisible()

    await page.getByPlaceholder("Search for a class").fill("first request")
    await expect(page.getByRole("alert")).toHaveText("Failed to load classes.")
    await page.getByPlaceholder("Search for a class").fill("Class")
    await expect(
        page.getByRole("article").filter({ hasText: "Class 8B" })
    ).toBeVisible()
    await expect(page.getByRole("alert")).toHaveCount(0)
})

test("a failed class deletion is explained inside its dialog, and nowhere else", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.route("**/api/classes/11", (route) =>
        route.request().method() === "DELETE"
            ? route.fulfill({ status: 500, json: {} })
            : route.fallback()
    )
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()

    await page.getByRole("button", { name: "Delete class" }).click()
    const dialog = page.getByRole("dialog", { name: "Delete class" })
    await dialog.getByRole("button", { name: "Delete" }).click()
    await expect(dialog).toContainText("Unable to perform this deletion.")
    await dialog.getByRole("button", { name: "Cancel" }).click()

    // The class form opened next starts without the deletion's message.
    await page.getByRole("button", { name: "New class" }).click()
    await expect(page.getByRole("dialog")).toBeVisible()
    await expect(
        page.getByText("Unable to perform this deletion.")
    ).toHaveCount(0)
})

test("printing one class's credentials leaves the other classes available", async ({
    page,
}) => {
    await mockTeacherApi(page)
    await page.route("**/api/classes?**", (route) =>
        route.fulfill({
            json: [
                existingClass,
                { ...existingClass, id: 12, name: "Class 8C" },
            ],
            headers: {
                "X-Page": "1",
                "X-Page-Size": "8",
                "X-Total-Count": "2",
            },
        })
    )
    // The credentials of the first class take their time.
    await page.route("**/api/students/credentials?class_id=11", () => {})
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()

    const cards = page.getByRole("article")
    await cards
        .filter({ hasText: "Class 8B" })
        .getByRole("button", { name: "Print credentials" })
        .click()

    await expect(
        cards
            .filter({ hasText: "Class 8B" })
            .getByRole("button", { name: "Print credentials" })
    ).toBeDisabled()
    await expect(
        cards
            .filter({ hasText: "Class 8C" })
            .getByRole("button", { name: "Print credentials" })
    ).toBeEnabled()
})

test("grade levels that fail to load say so and can be loaded again", async ({
    page,
}) => {
    await mockTeacherApi(page)
    // Fails until the test lets it through, however often it is asked.
    let failing = true
    await page.route("**/api/classes/grade-levels", async (route) => {
        if (route.request().method() === "GET" && failing)
            return route.fulfill({ status: 500, json: {} })
        return route.fallback()
    })
    await page.goto("/teacher/dashboard")

    await expect(page.getByRole("alert")).toContainText(
        "Failed to load grade levels"
    )
    failing = false
    await page.getByRole("button", { name: "Try again" }).click()
    await expect(page.getByRole("alert")).toHaveCount(0)

    await page.getByRole("button", { name: "Classes", exact: true }).click()
    await page.getByRole("button", { name: "New class" }).click()
    await expect(
        page.getByRole("dialog").getByRole("option", { name: "Grade 8" })
    ).toHaveCount(1)
})

test("Enter in the class dialog's student fields adds the student and keeps the dialog open", async ({
    page,
}) => {
    const requests = await mockTeacherApi(page)
    await page.goto("/teacher/dashboard")
    await page.getByRole("button", { name: "Classes", exact: true }).click()
    await page
        .getByRole("article")
        .filter({ hasText: "Class 8B" })
        .getByRole("button", { name: "Edit class" })
        .click()
    const dialog = page.getByRole("dialog", { name: "Edit class" })
    await dialog.getByLabel("First name").fill("Grace")
    await dialog.getByLabel("Last name").fill("Hopper")
    await dialog.getByLabel("Last name").press("Enter")

    await expect
        .poll(() =>
            requests.some(
                (request) =>
                    new URL(request.url()).pathname === "/api/students" &&
                    request.method() === "POST"
            )
        )
        .toBe(true)
    await expect(dialog).toBeVisible()
    await expect(dialog.getByLabel("First name")).toHaveValue("")
    expect(
        requests.some(
            (request) =>
                new URL(request.url()).pathname === "/api/classes/11/update"
        )
    ).toBe(false)
})

test("a created grade level takes the place the API gives it", async ({
    page,
}) => {
    await mockTeacherApi(page)
    // The API orders levels by database collation, which can differ from
    // any order the browser would compute: here the new level comes last.
    const levels = [{ id: 1, name: "Grade 8" }]
    await page.route("**/api/classes/grade-levels", async (route) => {
        const request = route.request()
        if (request.method() === "POST") {
            const created = {
                id: 2,
                name: (request.postDataJSON() as { name: string }).name,
            }
            levels.push(created)
            return route.fulfill({ status: 201, json: created })
        }
        return route.fulfill({ json: levels })
    })
    await page.goto("/teacher/dashboard?section=classes")
    await page.getByRole("button", { name: "New class" }).click()
    const dialog = page.getByRole("dialog")
    await dialog.getByRole("button", { name: "Add a level" }).click()
    await dialog.getByPlaceholder("Ex.: 5th", { exact: true }).fill("Alpha")
    await dialog.getByRole("button", { name: "Add", exact: true }).click()

    await expect(
        dialog.getByLabel("Grade level", { exact: true }).getByRole("option")
    ).toHaveText(["Choose a level", "Grade 8", "Alpha"])
})

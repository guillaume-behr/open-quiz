import { expect, test, type Page, type Request } from "@playwright/test"

const admin = {
    id: 1,
    username: "admin",
    display_name: "Site administrator",
    is_admin: true,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
}

const teacher = {
    id: 7,
    username: "grace",
    display_name: "Grace Hopper",
    is_admin: false,
    is_active: true,
    created_at: "2026-01-02T00:00:00Z",
}

async function mockAdminApi(page: Page) {
    const requests: Request[] = []
    let users = [admin, teacher]
    let reports = [
        {
            id: 19,
            message: "The results table is difficult to read on a phone.",
            page_path: "/teacher/dashboard",
            created_at: "2026-01-03T10:00:00Z",
        },
    ]

    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "en")
        sessionStorage.setItem("open-quiz-refresh-proof", "admin-proof")
    })
    await page.route(/^http:\/\/127\.0\.0\.1:4173\/api\//, async (route) => {
        const request = route.request()
        const url = new URL(request.url())
        requests.push(request)

        if (url.pathname === "/api/auth/refresh") {
            return route.fulfill({
                json: {
                    access_token: "admin-access-token",
                    refresh_proof: "rotated-admin-proof",
                },
            })
        }
        if (url.pathname === "/api/users/me") {
            return route.fulfill({ json: admin })
        }
        if (url.pathname === "/api/admin/users") {
            if (request.method() === "POST") {
                const body = request.postDataJSON() as {
                    username: string
                    display_name: string
                }
                const created = {
                    ...teacher,
                    id: 8,
                    username: body.username,
                    display_name: body.display_name,
                }
                users = [...users, created]
                return route.fulfill({ status: 201, json: created })
            }
            return route.fulfill({
                json: users,
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "8",
                    "X-Total-Count": String(users.length),
                },
            })
        }
        const statusMatch = url.pathname.match(
            /^\/api\/admin\/users\/(\d+)\/status$/
        )
        if (statusMatch) {
            const id = Number(statusMatch[1])
            const { is_active } = request.postDataJSON() as {
                is_active: boolean
            }
            const updated = {
                ...users.find((user) => user.id === id)!,
                is_active,
            }
            users = users.map((user) => (user.id === id ? updated : user))
            return route.fulfill({ json: updated })
        }
        const credentialsMatch = url.pathname.match(
            /^\/api\/admin\/users\/(\d+)\/credentials$/
        )
        if (credentialsMatch) {
            return route.fulfill({
                json: users.find(
                    (user) => user.id === Number(credentialsMatch[1])
                ),
            })
        }
        if (url.pathname === "/api/problem-reports") {
            return route.fulfill({
                json: reports,
                headers: {
                    "X-Page": "1",
                    "X-Page-Size": "8",
                    "X-Total-Count": String(reports.length),
                },
            })
        }
        const reportMatch = url.pathname.match(
            /^\/api\/problem-reports\/(\d+)$/
        )
        if (reportMatch && request.method() === "DELETE") {
            reports = reports.filter(
                (report) => report.id !== Number(reportMatch[1])
            )
            return route.fulfill({ status: 204 })
        }
        if (url.pathname === "/api/auth/logout") {
            return route.fulfill({ status: 204 })
        }
        return route.fulfill({ status: 404, json: {} })
    })

    return requests
}

test("administrator manages teachers and problem reports", async ({ page }) => {
    const requests = await mockAdminApi(page)
    await page.goto("/admin/dashboard")

    await expect(
        page.getByText("Logged in as Site administrator")
    ).toBeVisible()
    await expect(
        page.locator("header").getByRole("button", { name: "Log out" })
    ).toBeVisible()
    await expect(
        page.locator("header").getByRole("link", { name: "Homepage" })
    ).toHaveCount(0)
    await expect(page.getByText("Grace Hopper")).toBeVisible()

    await page.getByLabel("Display name").fill("Katherine Johnson")
    await page.getByLabel("Username").fill("katherine")
    await page
        .getByLabel("Password", { exact: true })
        .fill("a-secure-password-2026")
    await page.getByRole("button", { name: "Create user" }).click()

    await expect(page.getByText("Katherine Johnson")).toBeVisible()
    await expect(page.getByRole("status")).toHaveText(
        "User katherine has been created."
    )
    expect(
        requests
            .find(
                (request) =>
                    new URL(request.url()).pathname === "/api/admin/users" &&
                    request.method() === "POST"
            )
            ?.postDataJSON()
    ).toEqual({
        display_name: "Katherine Johnson",
        username: "katherine",
        password: "a-secure-password-2026",
    })

    const teacherRow = page
        .getByText("@grace", { exact: true })
        .locator("../..")
    await teacherRow.getByRole("button", { name: "Recover access" }).click()
    const recoveryDialog = page.getByRole("dialog", {
        name: "Recover access",
    })
    await recoveryDialog
        .getByLabel("New password")
        .fill("replacement-password-2026")
    await recoveryDialog.getByRole("button", { name: "Reset access" }).click()
    await expect(page.getByRole("status")).toHaveText(
        "Access for grace has been reset."
    )
    expect(
        requests
            .find((request) =>
                new URL(request.url()).pathname.endsWith("/7/credentials")
            )
            ?.postDataJSON()
    ).toEqual({
        password: "replacement-password-2026",
        reset_two_factor: true,
    })

    await teacherRow.getByRole("button", { name: "Disable" }).click()
    await expect(page.getByRole("status")).toHaveText(
        "Account grace has been deactivated and its sessions have been revoked."
    )
    await expect(teacherRow.getByText("Disabled")).toBeVisible()

    await page.getByRole("button", { name: /Problem reports/ }).click()
    await expect(
        page.getByRole("heading", { name: "Problem reports", exact: true })
    ).toHaveCount(1)
    await expect(
        page.getByText("The results table is difficult to read on a phone.")
    ).toBeVisible()
    const reportCard = page.getByRole("article").filter({
        hasText: "The results table is difficult to read on a phone.",
    })
    await reportCard.getByRole("button", { name: "Delete" }).click()
    let deleteDialog = page.getByRole("dialog", { name: "Delete" })
    await expect(deleteDialog).toContainText("Permanently delete this report?")
    const closingContent = await deleteDialog
        .getByRole("button", { name: "Cancel" })
        .evaluate((button) => {
            button.click()
            return button.closest('[role="dialog"]')?.textContent
        })
    expect(closingContent).toContain("Permanently delete this report?")
    await expect(deleteDialog).toBeHidden()

    await reportCard.getByRole("button", { name: "Delete" }).click()
    deleteDialog = page.getByRole("dialog", { name: "Delete" })
    await deleteDialog.getByRole("button", { name: "Delete" }).click()
    await expect(
        page.getByText("The results table is difficult to read on a phone.")
    ).toHaveCount(0)
    expect(
        requests.some(
            (request) =>
                new URL(request.url()).pathname === "/api/problem-reports/19" &&
                request.method() === "DELETE"
        )
    ).toBe(true)
})

test("changing the language does not restore the administrator session again", async ({
    page,
}) => {
    const requests = await mockAdminApi(page)
    await page.goto("/admin/dashboard")
    await expect(
        page.getByText("Logged in as Site administrator")
    ).toBeVisible()

    await page.getByRole("button", { name: "Change language" }).click()
    await page.getByRole("menuitem", { name: "Français" }).click()
    await expect(
        page.getByText("Connecté en tant que Site administrator")
    ).toBeVisible()

    expect(
        requests.filter(
            (request) => new URL(request.url()).pathname === "/api/auth/refresh"
        )
    ).toHaveLength(1)
})

test("a failed teacher deletion is explained inside its dialog", async ({
    page,
}) => {
    await mockAdminApi(page)
    await page.route("**/api/admin/users/7", (route) =>
        route.fulfill({ status: 500, json: {} })
    )
    await page.goto("/admin/dashboard")

    await page
        .getByText("@grace", { exact: true })
        .locator("../..")
        .getByRole("button", { name: "Delete" })
        .click()
    const dialog = page.getByRole("dialog", { name: "Delete the teacher" })
    await dialog.getByRole("button", { name: "Delete" }).click()

    await expect(dialog).toContainText("This teacher could not be deleted.")
    await dialog.getByRole("button", { name: "Cancel" }).click()
    await expect(dialog).toBeHidden()
    // The message stays with the dialog, not behind it on the page.
    await expect(
        page.getByText("This teacher could not be deleted.")
    ).toHaveCount(0)
})

test("a user list that fails to load says so and can be loaded again", async ({
    page,
}) => {
    await mockAdminApi(page)
    // Fails until the test lets it through, however often it is asked.
    let failing = true
    await page.route("**/api/admin/users?**", async (route) => {
        if (failing) return route.fulfill({ status: 500, json: {} })
        return route.fallback()
    })
    await page.goto("/admin/dashboard")

    await expect(page.getByRole("alert")).toContainText("Failed to load users.")
    await expect(page.getByText("0 accounts")).toHaveCount(0)

    failing = false
    await page.getByRole("button", { name: "Try again" }).click()

    await expect(page.getByText("Grace Hopper")).toBeVisible()
    await expect(page.getByText("2 accounts")).toBeVisible()
    await expect(page.getByRole("alert")).toHaveCount(0)
})

test("the browser blocks a username the API would refuse", async ({ page }) => {
    const requests = await mockAdminApi(page)
    await page.goto("/admin/dashboard")
    await page.getByLabel("Display name").fill("Katherine Johnson")
    await page.getByLabel("Username").fill("katherine johnson")
    await page
        .getByLabel("Password", { exact: true })
        .fill("a-secure-password-2026")
    await page.getByRole("button", { name: "Create user" }).click()

    await expect
        .poll(() =>
            page
                .getByLabel("Username")
                .evaluate((input: HTMLInputElement) => input.validity.valid)
        )
        .toBe(false)
    expect(
        requests.some(
            (request) =>
                new URL(request.url()).pathname === "/api/admin/users" &&
                request.method() === "POST"
        )
    ).toBe(false)
})

test("the admin section lives in the URL", async ({ page }) => {
    await mockAdminApi(page)
    await page.goto("/admin/dashboard")
    await page.getByRole("button", { name: /Problem reports/ }).click()
    await expect(page).toHaveURL(/[?&]section=reports\b/)
    await page.reload()
    await expect(
        page.getByRole("heading", { name: "Problem reports", exact: true })
    ).toBeVisible()
    await page.goBack()
    await expect(page.getByText("Grace Hopper")).toBeVisible()
})

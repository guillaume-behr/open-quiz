import { expect, test } from "@playwright/test"

test("keyboard navigation and login errors expose accessible context", async ({
    page,
}) => {
    await page.addInitScript(() => localStorage.setItem("i18nextLng", "en"))
    await page.route("**/api/student-auth/me", (route) =>
        route.fulfill({ status: 401, json: { detail: "Unauthorized" } })
    )
    await page.goto("/student/login")

    const skipLink = page.getByRole("link", { name: "Skip to content" })
    await skipLink.focus()
    await expect(skipLink).toBeFocused()
    await skipLink.press("Enter")
    await expect(page.getByRole("main")).toBeFocused()
    await expect(
        page.getByRole("navigation", {
            name: "Legal and support navigation",
        })
    ).toBeVisible()

    await page.route("**/api/auth/login", (route) =>
        route.fulfill({ status: 401, json: { detail: "Invalid credentials" } })
    )
    await page.getByRole("link", { name: "Teacher area" }).click()
    await expect(page.getByRole("main")).toBeFocused()

    const username = page.getByLabel("Username")
    const password = page.getByLabel("Password")
    await username.fill("invalid")
    await password.fill("invalid-password")
    await page.getByRole("button", { name: "Sign in" }).click()

    const error = page.getByRole("alert")
    await expect(error).toBeVisible()
    await expect(username).toHaveAttribute("aria-invalid", "true")
    await expect(username).toHaveAttribute("aria-describedby", "login-error")
    await expect(password).toHaveAttribute("aria-describedby", "login-error")
})

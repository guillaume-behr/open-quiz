import { expect, test, type Page } from "@playwright/test"

// Right-to-left regression guard. Cards pin their edit/delete buttons to the
// inline-end corner and reserve space for them with padding on the same side.
// If either reverts to a physical `right-*`/`pr-*` utility the two land on
// opposite sides in Arabic and long titles render underneath the buttons.

const teacher = {
    id: 7,
    username: "ada",
    display_name: "Ada Lovelace",
    is_admin: false,
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
}

// Long enough to fill the card and reach the action buttons.
const LONG_TITLE =
    "Contrôle de connaissances sur la thermodynamique appliquée aux moteurs"

const bank = {
    id: 21,
    grade_level: "Grade 8",
    chapter: LONG_TITLE,
    created_at: "2026-01-03T00:00:00Z",
    question_count: 30,
    easy_question_count: 10,
    medium_question_count: 10,
    hard_question_count: 10,
}

function pageOf(json: unknown) {
    return {
        json,
        headers: {
            "X-Page": "1",
            "X-Page-Size": "8",
            "X-Total-Count": "1",
        },
    }
}

async function mockArabicTeacher(page: Page) {
    await page.addInitScript(() => {
        localStorage.setItem("i18nextLng", "ar")
        sessionStorage.setItem("open-quiz-refresh-proof", "initial-proof")
    })
    await page.route(/^http:\/\/127\.0\.0\.1:4173\/api\//, async (route) => {
        const path = new URL(route.request().url()).pathname
        if (path === "/api/auth/refresh")
            return route.fulfill({
                json: { access_token: "t", refresh_proof: "r" },
            })
        if (path === "/api/users/me") return route.fulfill({ json: teacher })
        if (path === "/api/grade-levels")
            return route.fulfill({ json: [{ id: 1, name: "Grade 8" }] })
        if (path === "/api/question-banks") return route.fulfill(pageOf([bank]))
        if (path === "/api/quizzes")
            return route.fulfill(
                pageOf([
                    {
                        id: 31,
                        mode: "exam",
                        title: LONG_TITLE,
                        source_language: "en",
                        question_count: 10,
                        duration_seconds: 1800,
                        allow_previous_questions: false,
                        same_questions_for_all: true,
                        easy_question_count: 3,
                        medium_question_count: 4,
                        hard_question_count: 3,
                        question_banks: [bank],
                        created_at: "2026-01-04T00:00:00Z",
                    },
                ])
            )
        return route.fulfill({ json: [] })
    })
}

/** Card headings that visually collide with an absolutely positioned button. */
async function overlappingHeadings(page: Page) {
    return page.evaluate(() => {
        const collisions: string[] = []
        for (const card of document.querySelectorAll("li, div")) {
            const buttons = [
                ...card.querySelectorAll(":scope > button"),
            ].filter((button) => getComputedStyle(button).position === "absolute")
            if (buttons.length === 0) continue
            for (const heading of card.querySelectorAll("h3, h4")) {
                const range = document.createRange()
                range.selectNodeContents(heading)
                const text = range.getBoundingClientRect()
                if (text.width === 0) continue
                for (const button of buttons) {
                    const box = button.getBoundingClientRect()
                    const overlapX =
                        Math.min(text.right, box.right) -
                        Math.max(text.left, box.left)
                    const overlapY =
                        Math.min(text.bottom, box.bottom) -
                        Math.max(text.top, box.top)
                    if (overlapX > 1 && overlapY > 1) {
                        collisions.push(
                            `"${heading.textContent?.slice(0, 40)}" overlaps ` +
                                `"${button.getAttribute("aria-label")}" by ` +
                                `${Math.round(overlapX)}x${Math.round(overlapY)}px`
                        )
                    }
                }
            }
        }
        return collisions
    })
}

test("long card titles clear the action buttons in Arabic", async ({ page }) => {
    await mockArabicTeacher(page)
    await page.goto("/teacher/dashboard")
    await expect(page.locator("html")).toHaveAttribute("dir", "rtl")

    for (const section of ["اختبارات الامتحان", "بنوك الأسئلة"]) {
        await page
            .getByRole("button", { name: section, exact: true })
            .first()
            .click()
        await expect(page.getByText(LONG_TITLE).first()).toBeVisible()
        expect(await overlappingHeadings(page)).toEqual([])
    }
})

test("the password reveal button clears the field in Arabic", async ({
    page,
}) => {
    await page.addInitScript(() => localStorage.setItem("i18nextLng", "ar"))
    await page.goto("/teacher/login")

    const field = page.locator('input[type="password"]').first()
    await expect(field).toBeVisible()
    await field.fill("un-mot-de-passe-assez-long-pour-remplir")
    const reveal = page.getByRole("button", { name: /كلمة المرور/ }).first()
    await expect(reveal).toBeVisible()

    // In RTL the text starts at the right, so the button must sit on the left.
    const [fieldBox, revealBox] = await Promise.all([
        field.boundingBox(),
        reveal.boundingBox(),
    ])
    expect(fieldBox).not.toBeNull()
    expect(revealBox).not.toBeNull()
    expect(revealBox!.x).toBeLessThan(fieldBox!.x + fieldBox!.width / 2)
})

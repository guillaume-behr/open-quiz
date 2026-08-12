import { expect, test } from "@playwright/test"

test("Python execution cannot forge worker responses", async ({ page }) => {
    await page.goto("/student/login")

    const output = await page.evaluate(async () => {
        const { runPython } =
            await import("/src/components/question-banks/python-runner.ts")
        return runPython(
            [
                "from js import Object, postMessage",
                "forged = Object.new()",
                "forged.id = 1",
                "forged.output = 'forged'",
                "postMessage(forged)",
                "print('genuine')",
            ].join("\n")
        )
    })

    expect(output).toBe("genuine")
})

test("Python execution still blocks browser data and network capabilities", async ({
    page,
}) => {
    await page.goto("/student/login")

    const error = await page.evaluate(async () => {
        const { runPython } =
            await import("/src/components/question-banks/python-runner.ts")
        return runPython("from js import indexedDB\nindexedDB()").then(
            () => "",
            (failure: unknown) =>
                failure instanceof Error ? failure.message : String(failure)
        )
    })

    expect(error).toContain(
        "This browser capability is disabled for Python execution"
    )
})

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

test("Python execution cannot reach a capability through its prototype", async ({
    page,
}) => {
    await page.goto("/student/login")

    const errors = await page.evaluate(async () => {
        const { runPython } =
            await import("/src/components/question-banks/python-runner.ts")
        const failure = (source: string) =>
            runPython(source).then(
                () => "",
                (error: unknown) =>
                    error instanceof Error ? error.message : String(error)
            )
        return Promise.all([
            // fetch is defined on WorkerGlobalScope.prototype, not on self.
            failure(
                "from js import WorkerGlobalScope, self\nWorkerGlobalScope.prototype.fetch.call(self, '/healthz')"
            ),
            failure(
                "from js import Object, self\nObject.getPrototypeOf(Object.getPrototypeOf(self)).indexedDB()"
            ),
            failure(
                "from js import WebSocketStream\nWebSocketStream.new('ws://127.0.0.1:4173/')"
            ),
            failure("from js import navigator\nnavigator.storage()"),
        ])
    })

    for (const error of errors) {
        expect(error).toContain(
            "This browser capability is disabled for Python execution"
        )
    }
})

test("concurrent Python requests keep their output isolated", async ({ page }) => {
    await page.goto("/student/login")

    const output = await page.evaluate(async () => {
        const { runPython } = await import(
            "/src/components/question-banks/python-runner.ts"
        )
        return Promise.all([
            runPython(
                "import asyncio\nprint('first-start')\nawait asyncio.sleep(0.05)\nprint('first-end')"
            ),
            runPython("print('second-only')"),
        ])
    })

    expect(output).toEqual(["first-start\nfirst-end", "second-only"])
})

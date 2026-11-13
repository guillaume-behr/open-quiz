// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SubmittedAnswer } from "@/components/shared/submitted-answer"

describe("SubmittedAnswer", () => {
    afterEach(cleanup)

    it("joins text answers with commas", () => {
        render(
            <SubmittedAnswer
                values={["a", "b"]}
                language={null}
                placeholder="none"
            />
        )
        expect(screen.getByText("a, b")).toBeTruthy()
    })

    it("shows the placeholder when every value is blank", () => {
        render(
            <SubmittedAnswer
                values={["", "  "]}
                language="python"
                placeholder="none"
            />
        )
        expect(screen.getByText("none")).toBeTruthy()
    })

    it("shows code answers in a code block, one value per line", async () => {
        const { container } = render(
            <SubmittedAnswer
                values={["x = 1", "print(x)"]}
                language="python"
                placeholder="none"
            />
        )
        await vi.waitFor(() => {
            const code = container.querySelector("code")?.textContent ?? ""
            expect(code).toContain("x = 1")
            expect(code).toContain("print(x)")
        })
        expect(screen.queryByText("x = 1, print(x)")).toBeNull()
    })
})

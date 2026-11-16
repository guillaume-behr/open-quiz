// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { useState } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

// Counts Prism passes: each render of Highlight re-tokenises its whole code.
const highlighted = vi.hoisted(() => ({ codes: [] as string[] }))
vi.mock("prism-react-renderer", async (importOriginal) => {
    const actual = await importOriginal<typeof import("prism-react-renderer")>()
    return {
        ...actual,
        Highlight: (props: Parameters<typeof actual.Highlight>[0]) => {
            highlighted.codes.push(props.code)
            return <actual.Highlight {...props} />
        },
    }
})

vi.mock("@/components/code/python-runner", () => ({
    runPython: vi.fn((source: string) => Promise.resolve(`ran ${source}`)),
    describePythonFailure: () => "failure",
}))

import { CodeBlock } from "./code-block"

const questionCode = "def question():\n    return 42"

function ExamAnswer() {
    const [answer, setAnswer] = useState("print(1)")
    return (
        <>
            <CodeBlock code={questionCode} language="python" />
            <CodeBlock
                code={answer}
                language="python"
                editable
                onCodeChange={setAnswer}
            />
        </>
    )
}

describe("CodeBlock", () => {
    beforeEach(() => {
        highlighted.codes = []
    })

    it("highlights each keystroke once, and leaves other code blocks alone", () => {
        render(<ExamAnswer />)
        highlighted.codes = []

        const editor = screen.getByLabelText("source-code")
        fireEvent.change(editor, { target: { value: "print(12)" } })
        fireEvent.change(editor, { target: { value: "print(123)" } })

        expect(editor).toHaveValue("print(123)")
        expect(highlighted.codes).toEqual(["print(12)", "print(123)"])
        const [, answerRegion] = screen.getAllByRole("region", {
            name: "code-block-region",
        })
        expect(answerRegion).toHaveTextContent("print(123)")
    })

    it("does not highlight again when re-rendered with the same code", () => {
        const { rerender } = render(
            <CodeBlock code={questionCode} language="python" />
        )
        rerender(<CodeBlock code={questionCode} language="python" />)

        expect(highlighted.codes).toEqual([questionCode])
    })

    it("hides the output of a previous program when the code changes", async () => {
        const { rerender } = render(
            <CodeBlock code="print(1)" language="python" runnable />
        )
        fireEvent.click(screen.getByRole("button", { name: "run-python" }))
        await waitFor(() =>
            expect(screen.getByRole("status")).toHaveTextContent("ran print(1)")
        )

        rerender(<CodeBlock code="print(2)" language="python" runnable />)

        expect(screen.queryByRole("status")).not.toBeInTheDocument()
    })
})

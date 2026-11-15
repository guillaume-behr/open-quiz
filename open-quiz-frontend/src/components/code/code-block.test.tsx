// @vitest-environment jsdom
import { fireEvent, render, screen } from "@testing-library/react"
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
})

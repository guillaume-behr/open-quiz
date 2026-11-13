import type { CodeLanguage } from "@/api/types"
import { StaticCodeBlock } from "@/components/question-banks/code-block"

/**
 * The values of an answer, as a student submitted them or as expected: code
 * in a code block when the question asks for code, other answers joined by
 * commas, and `placeholder` when every value is blank.
 */
export function SubmittedAnswer({
    values,
    language,
    placeholder,
}: {
    values: string[]
    language?: CodeLanguage | null
    placeholder: string
}) {
    const isBlank = values.every((value) => value.trim() === "")
    if (!isBlank && language) {
        return (
            <div className="mt-2">
                <StaticCodeBlock code={values.join("\n")} language={language} />
            </div>
        )
    }
    return (
        <p className="mt-1 text-sm whitespace-pre-wrap">
            {isBlank ? placeholder : values.join(", ")}
        </p>
    )
}

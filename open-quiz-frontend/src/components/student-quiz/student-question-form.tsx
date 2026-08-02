import type { StudentQuizQuestion, StudentQuizSession } from "@/api/types"
import { CODE_LANGUAGES } from "@/components/question-banks/code-languages"
import { CodeBlock } from "@/components/question-banks/code-block"
import { Button } from "@/components/ui/button"
import { FieldError } from "@/components/ui/field"
import { cn } from "@/lib/utils"
import { LoaderCircle } from "lucide-react"
import type { FormEvent } from "react"
import { useTranslation } from "react-i18next"
import { ProtectedQuizImage } from "./protected-quiz-image"

type StudentQuestionFormProps = {
    session: StudentQuizSession
    question: StudentQuizQuestion
    participantToken: string
    selectedChoiceIds: number[]
    writtenAnswer: string
    isBusy: boolean
    error: string | null
    onSelectedChoiceIdsChange: (choiceIds: number[]) => void
    onWrittenAnswerChange: (answer: string) => void
    onPrevious: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function StudentQuestionForm({
    session,
    question,
    participantToken,
    selectedChoiceIds,
    writtenAnswer,
    isBusy,
    error,
    onSelectedChoiceIdsChange,
    onWrittenAnswerChange,
    onPrevious,
    onSubmit,
}: StudentQuestionFormProps) {
    const { t } = useTranslation()
    const progress =
        session.total_questions === 0
            ? 0
            : Math.round(
                  (session.answered_count / session.total_questions) * 100
              )

    return (
        <form className="space-y-5" onSubmit={onSubmit}>
            <p className="text-sm font-semibold text-primary">
                {t("student-question-progress", {
                    current: session.question_number,
                    total: session.total_questions,
                })}
            </p>
            <div
                className="h-2 overflow-hidden rounded-full bg-muted"
                role="progressbar"
                aria-valuenow={session.answered_count}
                aria-valuemin={0}
                aria-valuemax={session.total_questions}
                aria-label={t("student-answered-progress", {
                    count: session.answered_count,
                    total: session.total_questions,
                })}
            >
                <div
                    className="h-full rounded-full bg-primary transition-all"
                    style={{ width: `${progress}%` }}
                />
            </div>
            <p className="text-xs text-muted-foreground">
                {t("student-answered-progress", {
                    count: session.answered_count,
                    total: session.total_questions,
                })}
            </p>
            <h2 className="text-xl font-bold">{question.prompt}</h2>
            {question.has_image && (
                <ProtectedQuizImage
                    path="questions"
                    id={question.id}
                    joinCode={session.join_code}
                    token={participantToken}
                    alt={question.prompt}
                />
            )}
            {question.code_content && question.code_language && (
                <CodeBlock
                    code={question.code_content}
                    language={question.code_language}
                />
            )}
            {question.answer_mode === "written" ? (
                <WrittenAnswer
                    question={question}
                    answer={writtenAnswer}
                    onAnswerChange={onWrittenAnswerChange}
                />
            ) : (
                <ChoiceAnswers
                    question={question}
                    joinCode={session.join_code}
                    participantToken={participantToken}
                    selectedChoiceIds={selectedChoiceIds}
                    onSelectedChoiceIdsChange={onSelectedChoiceIdsChange}
                />
            )}
            {error && <FieldError>{error}</FieldError>}
            <div className="flex flex-col gap-3 sm:flex-row">
                {session.allow_previous_questions &&
                    (session.question_number ?? 1) > 1 && (
                        <Button
                            type="button"
                            variant="outline"
                            disabled={isBusy}
                            onClick={onPrevious}
                        >
                            {t("previous-question")}
                        </Button>
                    )}
                <Button
                    className="flex-1"
                    size="lg"
                    type="submit"
                    disabled={
                        isBusy ||
                        (question.answer_mode === "written"
                            ? writtenAnswer.trim().length === 0
                            : selectedChoiceIds.length === 0)
                    }
                >
                    {isBusy && <LoaderCircle className="animate-spin" />}
                    {t("student-submit-answer")}
                </Button>
            </div>
        </form>
    )
}

function WrittenAnswer({
    question,
    answer,
    onAnswerChange,
}: {
    question: StudentQuizQuestion
    answer: string
    onAnswerChange: (answer: string) => void
}) {
    const { t } = useTranslation()
    const responseLanguage = question.response_language
    const languageLabel = responseLanguage
        ? (CODE_LANGUAGES.find((item) => item.value === responseLanguage)
              ?.label ?? responseLanguage)
        : null

    return (
        <div className="space-y-2">
            <p className="text-sm text-muted-foreground">
                {languageLabel
                    ? t("write-code-in-language", { language: languageLabel })
                    : t("plain-text-response")}
            </p>
            {responseLanguage ? (
                <CodeBlock
                    code={answer}
                    language={responseLanguage}
                    editable
                    onCodeChange={onAnswerChange}
                    editorClassName="min-h-48"
                    required
                />
            ) : (
                <textarea
                    className="min-h-32 w-full rounded-md border bg-background p-3"
                    value={answer}
                    aria-label={t("written-answer")}
                    spellCheck
                    onChange={(event) => onAnswerChange(event.target.value)}
                    maxLength={20000}
                    required
                />
            )}
        </div>
    )
}

function ChoiceAnswers({
    question,
    joinCode,
    participantToken,
    selectedChoiceIds,
    onSelectedChoiceIdsChange,
}: {
    question: StudentQuizQuestion
    joinCode: string
    participantToken: string
    selectedChoiceIds: number[]
    onSelectedChoiceIdsChange: (choiceIds: number[]) => void
}) {
    function toggleChoice(choiceId: number) {
        if (question.answer_mode === "single") {
            onSelectedChoiceIdsChange([choiceId])
            return
        }
        onSelectedChoiceIdsChange(
            selectedChoiceIds.includes(choiceId)
                ? selectedChoiceIds.filter((id) => id !== choiceId)
                : [...selectedChoiceIds, choiceId]
        )
    }

    return (
        <div className="grid gap-3">
            {question.choices.map((choice) => {
                const checked = selectedChoiceIds.includes(choice.id)
                return (
                    <label
                        key={choice.id}
                        className={cn(
                            "flex cursor-pointer gap-3 rounded-xl border bg-background p-4 transition-colors focus-within:border-primary focus-within:ring-3 focus-within:ring-primary/20 hover:border-primary/50 hover:bg-primary/5",
                            checked && "border-primary bg-primary/10"
                        )}
                    >
                        <input
                            className="mt-1 accent-primary"
                            type={
                                question.answer_mode === "single"
                                    ? "radio"
                                    : "checkbox"
                            }
                            name="answer"
                            checked={checked}
                            onChange={() => toggleChoice(choice.id)}
                        />
                        <span className="min-w-0 flex-1">
                            {choice.label}
                            {choice.has_image && (
                                <ProtectedQuizImage
                                    path="choices"
                                    id={choice.id}
                                    joinCode={joinCode}
                                    token={participantToken}
                                    alt={choice.label}
                                />
                            )}
                            {choice.code_content && (
                                <pre
                                    className="mt-2 overflow-x-auto rounded bg-slate-950 p-3 text-left text-sm text-slate-50"
                                    dir="ltr"
                                >
                                    <code>{choice.code_content}</code>
                                </pre>
                            )}
                        </span>
                    </label>
                )
            })}
        </div>
    )
}

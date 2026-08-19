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
    contentDirection: "ltr" | "rtl"
    selectedChoiceIds: number[]
    writtenAnswer: string
    isBusy: boolean
    error: string | null
    onSelectedChoiceIdsChange: (choiceIds: number[]) => void
    onWrittenAnswerChange: (answer: string) => void
    onNavigate: (questionNumber: number) => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
}

export function StudentQuestionForm({
    session,
    question,
    participantToken,
    contentDirection,
    selectedChoiceIds,
    writtenAnswer,
    isBusy,
    error,
    onSelectedChoiceIdsChange,
    onWrittenAnswerChange,
    onNavigate,
    onSubmit,
}: StudentQuestionFormProps) {
    const { t } = useTranslation()
    const questionNumber = session.question_number ?? 1
    const progress =
        session.total_questions === 0
            ? 0
            : Math.round((questionNumber / session.total_questions) * 100)

    return (
        <form className="space-y-6" onSubmit={onSubmit}>
            <div className="space-y-2">
                <div className="flex items-baseline">
                    <p className="text-sm font-semibold text-primary">
                        {t("student-question-progress", {
                            current: questionNumber,
                            total: session.total_questions,
                        })}
                    </p>
                </div>
                <div
                    className="h-2 overflow-hidden rounded-full bg-muted"
                    role="progressbar"
                    aria-valuenow={questionNumber}
                    aria-valuemin={1}
                    aria-valuemax={session.total_questions}
                    aria-label={t("student-question-progress", {
                        current: questionNumber,
                        total: session.total_questions,
                    })}
                >
                    <div
                        className="h-full rounded-full bg-primary transition-all"
                        style={{ width: `${progress}%` }}
                    />
                </div>
            </div>
            <h2
                className="w-full text-2xl leading-relaxed font-bold text-balance"
                dir={contentDirection}
            >
                {question.prompt}
            </h2>
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
                    contentDirection={contentDirection}
                    selectedChoiceIds={selectedChoiceIds}
                    onSelectedChoiceIdsChange={onSelectedChoiceIdsChange}
                />
            )}
            {error && <FieldError>{error}</FieldError>}
            <div
                className="flex min-w-0 items-center justify-end gap-3 border-t pt-5"
                dir="ltr"
            >
                {session.allow_previous_questions && (
                    <nav
                        className="min-w-0 flex-1 overflow-x-auto"
                        aria-label={t("student-question-progress", {
                            current: questionNumber,
                            total: session.total_questions,
                        })}
                    >
                        <div className="flex w-max gap-2 py-1">
                            {session.accessible_question_numbers.map(
                                (number) => {
                                    const isCurrent = number === questionNumber
                                    return (
                                        <Button
                                            key={number}
                                            className="size-10 shrink-0 p-0"
                                            type="button"
                                            variant={
                                                isCurrent
                                                    ? "default"
                                                    : "outline"
                                            }
                                            aria-current={
                                                isCurrent ? "step" : undefined
                                            }
                                            aria-label={t(
                                                "student-question-progress",
                                                {
                                                    current: number,
                                                    total: session.total_questions,
                                                }
                                            )}
                                            disabled={isBusy || isCurrent}
                                            onClick={() => onNavigate(number)}
                                        >
                                            {number}
                                        </Button>
                                    )
                                }
                            )}
                        </div>
                    </nav>
                )}
                <Button
                    className="shrink-0 sm:min-w-64"
                    size="lg"
                    type="submit"
                    dir="auto"
                    disabled={
                        isBusy ||
                        (question.answer_mode === "written"
                            ? writtenAnswer.trim().length === 0
                            : selectedChoiceIds.length === 0)
                    }
                >
                    {isBusy && (
                        <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                    )}
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
        <section className="space-y-3" aria-labelledby="written-answer-label">
            <p
                id="written-answer-label"
                className="text-sm font-medium text-muted-foreground"
            >
                {languageLabel
                    ? t("write-code-in-language", { language: languageLabel })
                    : t("plain-text-response")}
            </p>
            {responseLanguage ? (
                <div className="w-full">
                    <CodeBlock
                        code={answer}
                        language={responseLanguage}
                        editable
                        runnable={question.allow_code_execution}
                        onCodeChange={onAnswerChange}
                        editorClassName="min-h-96 lg:min-h-[32rem]"
                        required
                    />
                </div>
            ) : (
                <textarea
                    className="block min-h-64 w-full resize-y rounded-xl border bg-background p-4 text-base leading-7 shadow-xs transition-shadow outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 lg:min-h-80"
                    value={answer}
                    aria-label={t("written-answer")}
                    spellCheck
                    onChange={(event) => onAnswerChange(event.target.value)}
                    maxLength={20000}
                    required
                />
            )}
        </section>
    )
}

function ChoiceAnswers({
    question,
    joinCode,
    participantToken,
    contentDirection,
    selectedChoiceIds,
    onSelectedChoiceIdsChange,
}: {
    question: StudentQuizQuestion
    joinCode: string
    participantToken: string
    contentDirection: "ltr" | "rtl"
    selectedChoiceIds: number[]
    onSelectedChoiceIdsChange: (choiceIds: number[]) => void
}) {
    const { t } = useTranslation()

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

    const answerModeHelpId = `question-${question.id}-answer-mode-help`

    return (
        <fieldset aria-describedby={answerModeHelpId}>
            <legend className="text-base font-semibold">
                {t("answer-choices")}
            </legend>
            <p
                id={answerModeHelpId}
                className="mt-1 mb-3 text-sm text-muted-foreground"
            >
                {t(
                    question.answer_mode === "single"
                        ? "single-choice"
                        : "multiple-choice"
                )}
            </p>
            <div className="grid items-stretch gap-3 sm:grid-cols-2">
                {question.choices.map((choice) => {
                    const checked = selectedChoiceIds.includes(choice.id)
                    return (
                        <label
                            key={choice.id}
                            className={cn(
                                "flex min-h-24 cursor-pointer select-none items-start gap-3 rounded-xl border bg-background p-4 shadow-xs transition-colors focus-within:border-primary focus-within:ring-3 focus-within:ring-primary/20 hover:border-primary/50 hover:bg-primary/5",
                                checked &&
                                    "border-primary bg-primary/10 ring-1 ring-primary/30"
                            )}
                        >
                            <input
                                className="mt-0.5 size-5 shrink-0 accent-primary"
                                type={
                                    question.answer_mode === "single"
                                        ? "radio"
                                        : "checkbox"
                                }
                                name="answer"
                                checked={checked}
                                onChange={() => toggleChoice(choice.id)}
                            />
                            <span
                                className="min-w-0 flex-1 leading-6 break-words"
                                dir={contentDirection}
                            >
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
        </fieldset>
    )
}

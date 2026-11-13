import { richTextToPlainText } from "@/lib/rich-text"
import { RichText } from "@/components/ui/rich-text"
import type { StudentQuizQuestion, StudentQuizSession } from "@/api/types"
import { CODE_LANGUAGES } from "@/components/question-banks/code-languages"
import {
    CodeBlock,
    StaticCodeBlock,
} from "@/components/question-banks/code-block"
import { indentCode } from "@/components/question-banks/code-editor-utils"
import { Button } from "@/components/ui/button"
import { FieldError } from "@/components/ui/field"
import { cn } from "@/lib/utils"
import { ChevronLeft, ChevronRight, LoaderCircle } from "lucide-react"
import { type FormEvent, useEffect, useRef, useState } from "react"
import { createPortal } from "react-dom"
import { useTranslation } from "react-i18next"
import { ProtectedQuizImage } from "./protected-quiz-image"

type StudentQuestionFormProps = {
    session: StudentQuizSession
    question: StudentQuizQuestion
    participantToken: string
    contentDirection: "ltr" | "rtl"
    selectedChoiceIds: string[]
    writtenAnswer: string
    isBusy: boolean
    error: string | null
    onSelectedChoiceIdsChange: (choiceIds: string[]) => void
    onWrittenAnswerChange: (answer: string) => void
    onNavigate: (questionNumber: number) => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
    /** Skips the question; without it, no skip button is offered. */
    onSkip?: () => void
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
    onSkip,
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
                <div className="flex items-baseline justify-between gap-3">
                    <p className="text-sm font-semibold text-primary">
                        {t("student-question-progress", {
                            current: questionNumber,
                            total: session.total_questions,
                        })}
                    </p>
                    {question.total_points != null && (
                        <p className="shrink-0 rounded-full border border-primary/30 bg-primary/10 px-2.5 py-0.5 text-sm font-semibold text-primary tabular-nums">
                            {t("student-question-points", {
                                count: question.total_points,
                            })}
                        </p>
                    )}
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
                className="w-full text-2xl leading-relaxed font-medium text-balance"
                dir={contentDirection}
            >
                <RichText text={question.prompt} />
            </h2>
            {question.has_image && (
                <ProtectedQuizImage
                    path="questions"
                    id={question.id}
                    joinCode={session.join_code}
                    token={participantToken}
                    alt={richTextToPlainText(question.prompt)}
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
                className="flex min-w-0 items-center justify-between gap-3 border-t pt-5"
                dir="ltr"
            >
                {onSkip ? (
                    <Button
                        className="shrink-0"
                        size="lg"
                        type="button"
                        variant="outline"
                        dir="auto"
                        disabled={isBusy}
                        onClick={onSkip}
                    >
                        {t("student-skip-question")}
                    </Button>
                ) : (
                    // Keeps the submit button on the right.
                    <span />
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
            {session.allow_previous_questions && (
                <QuestionNavigation
                    session={session}
                    isBusy={isBusy}
                    onNavigate={onNavigate}
                />
            )}
        </form>
    )
}

/** How many question numbers the navigation bar shows at once. */
const QUESTION_NAVIGATION_PAGE_SIZE = 10

/**
 * The numbered back-navigation, outside the question card: a bar fixed at
 * the bottom centre of the screen, so it stays in reach on a long question.
 * Portalled to the body so no ancestor's transform can unpin it.
 *
 * Every question is numbered, ten at a time with arrows beyond that: the
 * current one in the primary colour, skipped ones in orange (even once
 * answered), answered ones plain, the ones reached but unanswered in grey,
 * and those not seen yet in dark grey, disabled.
 *
 * Reaching a question on another page of ten turns the page by itself, and
 * every page turn slides the numbers in from the side it comes from.
 */
function QuestionNavigation({
    session,
    isBusy,
    onNavigate,
}: {
    session: StudentQuizSession
    isBusy: boolean
    onNavigate: (questionNumber: number) => void
}) {
    const { t } = useTranslation()
    const questionNumber = session.question_number ?? 1
    const total = session.total_questions
    const pageCount = Math.max(
        1,
        Math.ceil(total / QUESTION_NAVIGATION_PAGE_SIZE)
    )
    const currentPage = Math.floor(
        (questionNumber - 1) / QUESTION_NAVIGATION_PAGE_SIZE
    )
    // The page the student browsed to, until the question changes: moving
    // to another question brings back the page that holds it.
    const [browsed, setBrowsed] = useState({
        questionNumber,
        page: currentPage,
    })
    const page =
        browsed.questionNumber === questionNumber
            ? Math.min(browsed.page, pageCount - 1)
            : currentPage
    const showPage = (next: number) =>
        setBrowsed({ questionNumber, page: next })
    // The direction of the last page turn, for the slide. Updated during
    // render, as React recommends for state derived from a change.
    const [turn, setTurn] = useState({ page, direction: 0 })
    if (turn.page !== page)
        setTurn({ page, direction: page > turn.page ? 1 : -1 })

    const first = page * QUESTION_NAVIGATION_PAGE_SIZE + 1
    const numbers = Array.from(
        { length: Math.min(QUESTION_NAVIGATION_PAGE_SIZE, total - first + 1) },
        (_, index) => first + index
    )
    // On a narrow screen the numbers scroll: bring the current one into view
    // when the question or the page changes, not while the student scrolls.
    const currentNumber = useRef<HTMLButtonElement>(null)
    useEffect(() => {
        // Optional call: jsdom has no scrollIntoView.
        currentNumber.current?.scrollIntoView?.({
            block: "nearest",
            inline: "center",
        })
    }, [questionNumber, page])

    const accessible = new Set(session.accessible_question_numbers)
    const answered = new Set(session.answered_question_numbers)
    const skipped = new Set(session.skipped_question_numbers)

    return createPortal(
        <div
            className="pointer-events-none fixed inset-x-0 bottom-0 z-20 flex justify-center px-4 pb-4"
            dir="ltr"
        >
            <nav
                className="pointer-events-auto flex max-w-full items-center gap-1 rounded-2xl border bg-secondary px-2 py-2 shadow-lg sm:px-3"
                aria-label={t("student-question-progress", {
                    current: questionNumber,
                    total,
                })}
            >
                {pageCount > 1 && (
                    <Button
                        className="size-10 shrink-0"
                        type="button"
                        variant="ghost"
                        aria-label={t("student-question-navigation-previous")}
                        disabled={page === 0}
                        onClick={() => showPage(page - 1)}
                    >
                        <ChevronLeft className="size-5" />
                    </Button>
                )}
                <div
                    key={page}
                    className={cn(
                        // On a narrow screen the numbers scroll between the
                        // arrows, which stay in reach.
                        "flex min-w-0 gap-1.5 overflow-x-auto py-1 sm:gap-2",
                        turn.direction !== 0 &&
                            "animate-in duration-300 ease-out fade-in-0 motion-reduce:animate-none",
                        turn.direction > 0 && "slide-in-from-right-8",
                        turn.direction < 0 && "slide-in-from-left-8"
                    )}
                >
                    {numbers.map((number) => {
                        const isCurrent = number === questionNumber
                        const isSeen = accessible.has(number)
                        const isSkipped = !isCurrent && skipped.has(number)
                        return (
                            <Button
                                key={number}
                                ref={isCurrent ? currentNumber : undefined}
                                className={cn(
                                    "size-9 shrink-0 p-0 sm:size-10",
                                    !isCurrent &&
                                        !isSkipped &&
                                        isSeen &&
                                        !answered.has(number) &&
                                        "border-transparent bg-muted text-muted-foreground",
                                    isSkipped &&
                                        "border-transparent bg-orange-200 text-orange-950 hover:bg-orange-300 hover:text-orange-950 dark:bg-orange-400/30 dark:text-orange-100 dark:hover:bg-orange-400/40",
                                    !isSeen &&
                                        "border-transparent bg-muted-foreground/70 text-background disabled:opacity-100"
                                )}
                                type="button"
                                variant={isCurrent ? "default" : "outline"}
                                aria-current={isCurrent ? "step" : undefined}
                                // The state is said, not only coloured.
                                aria-label={[
                                    t("student-question-progress", {
                                        current: number,
                                        total,
                                    }),
                                    isCurrent
                                        ? null
                                        : t(
                                              !isSeen
                                                  ? "student-question-state-unseen"
                                                  : isSkipped
                                                    ? "student-question-state-skipped"
                                                    : answered.has(number)
                                                      ? "student-question-state-answered"
                                                      : "student-question-state-unanswered"
                                          ),
                                ]
                                    .filter(Boolean)
                                    .join(", ")}
                                disabled={isBusy || isCurrent || !isSeen}
                                onClick={() => onNavigate(number)}
                            >
                                {number}
                            </Button>
                        )
                    })}
                </div>
                {pageCount > 1 && (
                    <Button
                        className="size-10 shrink-0"
                        type="button"
                        variant="ghost"
                        aria-label={t("student-question-navigation-next")}
                        disabled={page === pageCount - 1}
                        onClick={() => showPage(page + 1)}
                    >
                        <ChevronRight className="size-5" />
                    </Button>
                )}
            </nav>
        </div>,
        document.body
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
                        onCodeKeyDown={(event) =>
                            indentCode(event, answer, onAnswerChange)
                        }
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
    selectedChoiceIds: string[]
    onSelectedChoiceIdsChange: (choiceIds: string[]) => void
}) {
    const { t } = useTranslation()

    function toggleChoice(choiceId: string) {
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
                    !question.answer_mode_disclosed
                        ? "answer-mode-not-disclosed"
                        : question.answer_mode === "single"
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
                                "flex min-h-24 cursor-pointer items-start gap-3 rounded-xl border bg-background p-4 shadow-xs transition-colors select-none focus-within:border-primary focus-within:ring-3 focus-within:ring-primary/20 hover:border-primary/50 hover:bg-primary/5",
                                checked &&
                                    "border-primary bg-primary/10 ring-1 ring-primary/30"
                            )}
                        >
                            <input
                                className="mt-0.5 size-5 shrink-0 accent-primary"
                                type={
                                    question.answer_mode_disclosed &&
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
                                        alt={choice.label || t("choice-image")}
                                    />
                                )}
                                {choice.code_content &&
                                    choice.code_language && (
                                        <div className="mt-2">
                                            <StaticCodeBlock
                                                code={choice.code_content}
                                                language={choice.code_language}
                                            />
                                        </div>
                                    )}
                            </span>
                        </label>
                    )
                })}
            </div>
        </fieldset>
    )
}

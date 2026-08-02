import type { Question, QuestionBank } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    ImageIcon,
    LoaderCircle,
    Pencil,
    Plus,
    Settings2,
    Trash2,
} from "lucide-react"
import { useTranslation } from "react-i18next"
import { ChoiceImage } from "./choice-image"
import { CodeBlock } from "./code-block"
import { CODE_LANGUAGES } from "./code-languages"
import { QuestionImage } from "./question-image"

type QuestionsDialogProps = {
    bank: QuestionBank
    questions: Question[]
    open: boolean
    isLoading: boolean
    error: string | null
    onOpenChange: (open: boolean) => void
    onAdd: () => void
    onEdit: (question: Question) => void
    onDelete: (question: Question) => void
}

export function QuestionsDialog({
    bank,
    questions,
    open,
    isLoading,
    error,
    onOpenChange,
    onAdd,
    onEdit,
    onDelete,
}: QuestionsDialogProps) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={open}
            onOpenChange={onOpenChange}
            title={bank.chapter}
            description={`${bank.grade_level} — ${t("bank-questions")}`}
        >
            <div className="flex flex-wrap justify-end gap-2">
                <Button type="button" onClick={onAdd}>
                    <Plus />
                    {t("add-question")}
                </Button>
            </div>
            <div className="mt-5">
                <h4 className="font-semibold">{t("bank-questions")}</h4>
                {isLoading ? (
                    <div className="flex min-h-24 items-center justify-center">
                        <LoaderCircle className="size-6 animate-spin text-primary" />
                    </div>
                ) : error ? (
                    <p role="alert" className="mt-3 text-sm text-destructive">
                        {error}
                    </p>
                ) : questions.length === 0 ? (
                    <p className="mt-3 rounded-xl border border-dashed p-5 text-center text-sm text-muted-foreground">
                        {t("no-question")}
                    </p>
                ) : (
                    <ol className="mt-3 space-y-3">
                        {questions.map((question, index) => (
                            <QuestionCard
                                key={question.id}
                                question={question}
                                index={index}
                                onEdit={() => onEdit(question)}
                                onDelete={() => onDelete(question)}
                            />
                        ))}
                    </ol>
                )}
            </div>
        </Dialog>
    )
}

function QuestionCard({
    question,
    index,
    onEdit,
    onDelete,
}: {
    question: Question
    index: number
    onEdit: () => void
    onDelete: () => void
}) {
    const { t } = useTranslation()
    return (
        <li className="rounded-xl border bg-background p-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                <p className="min-w-0 font-semibold break-words">
                    {index + 1}. {question.prompt}
                </p>
                <div className="flex shrink-0 flex-wrap items-center gap-2">
                    <span className="rounded-full bg-muted px-2 py-1 text-xs whitespace-nowrap">
                        {t(`difficulty-${question.difficulty}`)}
                    </span>
                    <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={onEdit}
                    >
                        <Pencil />
                        {t("edit")}
                    </Button>
                    <Button
                        type="button"
                        size="icon"
                        variant="destructive"
                        aria-label={t("delete-question")}
                        title={t("delete-question")}
                        onClick={onDelete}
                    >
                        <Trash2 />
                    </Button>
                </div>
            </div>
            {question.has_image && (
                <>
                    <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                        <ImageIcon className="size-3.5" />
                        {t("image-attached")}
                    </div>
                    <QuestionImage
                        questionId={question.id}
                        alt={question.prompt}
                    />
                </>
            )}
            {question.code_content && question.code_language && (
                <div className="mt-3">
                    <CodeBlock
                        code={question.code_content}
                        language={question.code_language}
                    />
                </div>
            )}
            <ul
                className={`mt-3 grid gap-2 ${
                    question.answer_mode === "written" ? "" : "sm:grid-cols-2"
                }`}
            >
                {question.choices.map((choice) => (
                    <li
                        key={choice.id}
                        className="rounded-lg bg-muted/60 px-3 py-2 text-sm"
                    >
                        <div className="flex items-center gap-2">
                            {question.answer_mode !== "written" && (
                                <span
                                    className={
                                        choice.is_correct
                                            ? "text-primary"
                                            : "text-muted-foreground"
                                    }
                                >
                                    {choice.is_correct ? "✓" : "○"}
                                </span>
                            )}
                            <span className="min-w-0 flex-1 whitespace-pre-wrap">
                                {question.answer_mode === "written" && (
                                    <span className="mb-1 block text-xs font-semibold text-muted-foreground">
                                        {t("expected-written-answer")}
                                    </span>
                                )}
                                {choice.label}
                            </span>
                        </div>
                        {choice.has_image && (
                            <ChoiceImage
                                choiceId={choice.id}
                                alt={choice.label}
                            />
                        )}
                        {choice.code_content && choice.code_language && (
                            <div className="mt-2">
                                <CodeBlock
                                    code={choice.code_content}
                                    language={choice.code_language}
                                />
                            </div>
                        )}
                    </li>
                ))}
            </ul>
            <QuestionMetadata question={question} />
        </li>
    )
}

function QuestionMetadata({ question }: { question: Question }) {
    const { t } = useTranslation()
    const answerModeKey =
        question.answer_mode === "single"
            ? "single-choice"
            : question.answer_mode === "multiple"
              ? "multiple-choice"
              : "written-answer"
    const responseLanguage = question.response_language
        ? (CODE_LANGUAGES.find(
              (language) => language.value === question.response_language
          )?.label ?? question.response_language)
        : t("plain-text")

    return (
        <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
                <Settings2 className="size-3.5" />
                {t(answerModeKey)}
            </span>
            {question.answer_mode === "written" && (
                <>
                    <span>•</span>
                    <span>{responseLanguage}</span>
                </>
            )}
            {!question.answer_mode_disclosed && (
                <>
                    <span>•</span>
                    <span>{t("answer-mode-not-disclosed")}</span>
                </>
            )}
        </div>
    )
}

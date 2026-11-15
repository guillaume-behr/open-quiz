import { richTextToPlainText } from "@/lib/rich-text"
import { questionMaxPoints } from "@/lib/questions"
import { RichText } from "@/components/ui/rich-text"
import type { Question } from "@/api/types"
import { Collapsible as CollapsiblePrimitive } from "@base-ui/react/collapsible"
import { Button } from "@/components/ui/button"
import { ImageIcon, ChevronDown, Pencil, Settings2, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { ChoiceImage } from "./choice-image"
import { CodeBlock } from "./code-block"
import { CODE_LANGUAGES } from "./code-languages"
import { QuestionImage } from "./question-image"

/** One question of a bank: its summary, and its details once expanded. */
export function QuestionCard({
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
    const detailsId = `question-details-${question.id}`
    return (
        <CollapsiblePrimitive.Root
            render={<li />}
            className="overflow-hidden rounded-xl border bg-background"
        >
            <div className="flex flex-col gap-1 p-2 sm:flex-row sm:items-stretch">
                <CollapsiblePrimitive.Trigger className="group flex min-w-0 flex-1 cursor-pointer items-center gap-2 rounded-lg px-3 py-2.5 text-start font-semibold break-words transition-colors select-none hover:bg-muted/70 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none focus-visible:ring-inset data-panel-open:bg-muted/40">
                    <ChevronDown className="size-4 shrink-0 transition-transform duration-200 ease-out group-data-panel-open:rotate-180 motion-reduce:transition-none" />
                    <span className="min-w-0 flex-1 font-medium">
                        {index + 1}. <RichText text={question.prompt} />
                    </span>
                    <span className="rounded-full bg-muted px-2 py-1 text-xs font-normal whitespace-nowrap">
                        {t(`difficulty-${question.difficulty}`)}
                    </span>
                    <span className="rounded-full bg-primary/10 px-2 py-1 text-xs font-semibold whitespace-nowrap text-primary">
                        {t("points-count", {
                            count: questionMaxPoints(question),
                        })}
                    </span>
                </CollapsiblePrimitive.Trigger>
                <div className="flex shrink-0 flex-wrap items-center gap-2 px-2 pt-1 pb-1 sm:p-1">
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
            <CollapsiblePrimitive.Panel
                id={detailsId}
                className="h-[var(--collapsible-panel-height)] overflow-hidden opacity-100 transition-[height,opacity] duration-200 ease-out data-ending-style:h-0 data-ending-style:opacity-0 data-starting-style:h-0 data-starting-style:opacity-0 motion-reduce:transition-none [&[hidden]:not([hidden='until-found'])]:hidden"
            >
                <div className="border-t px-4 pb-4">
                    {question.has_image && (
                        <>
                            <div className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
                                <ImageIcon className="size-3.5" />
                                {t("image-attached")}
                            </div>
                            <QuestionImage
                                questionId={question.id}
                                alt={richTextToPlainText(question.prompt)}
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
                            question.answer_mode === "written"
                                ? ""
                                : "sm:grid-cols-2"
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
                                    <span className="font-semibold">
                                        {t("points-count", {
                                            count: choice.points,
                                        })}
                                    </span>
                                </div>
                                {choice.has_image && (
                                    <ChoiceImage
                                        choiceId={choice.id}
                                        alt={choice.label || t("choice-image")}
                                    />
                                )}
                                {choice.code_content &&
                                    choice.code_language && (
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
                </div>
            </CollapsiblePrimitive.Panel>
        </CollapsiblePrimitive.Root>
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

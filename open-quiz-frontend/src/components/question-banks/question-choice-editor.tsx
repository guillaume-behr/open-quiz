import type { AnswerMode, CodeLanguage } from "@/api/types"
import { Button } from "@/components/ui/button"
import { FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { Textarea } from "@/components/ui/textarea"
import { Code2, ImagePlus, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"
import { CodeBlock } from "./code-block"
import { CODE_LANGUAGES } from "./code-languages"
import { indentCode } from "./code-editor-utils"
import type { EditableChoice } from "./question-form-types"
import { SelectedImagePreview } from "./selected-image-preview"

type QuestionChoiceEditorProps = {
    choice: EditableChoice
    index: number
    choiceCount: number
    answerMode: AnswerMode
    responseLanguage: CodeLanguage | null
    onUpdate: (update: Partial<EditableChoice>) => void
    onCorrectChange: (checked: boolean) => void
    onRemove: () => void
}

export function QuestionChoiceEditor({
    choice,
    index,
    choiceCount,
    answerMode,
    responseLanguage,
    onUpdate,
    onCorrectChange,
    onRemove,
}: QuestionChoiceEditorProps) {
    const { t } = useTranslation()

    if (answerMode === "written") {
        return (
            <div className="space-y-3 rounded-lg border p-3">
                <div className="max-w-40">
                    <FieldLabel htmlFor={`written-points-${index}`}>
                        {t("points")}
                    </FieldLabel>
                    <Input
                        id={`written-points-${index}`}
                        className="mt-2"
                        type="number"
                        min={0}
                        max={10000}
                        step="0.25"
                        value={choice.points}
                        onChange={(event) =>
                            onUpdate({ points: Number(event.target.value) })
                        }
                        required
                    />
                </div>
                <ChoiceValueField
                    choice={choice}
                    index={index}
                    answerMode={answerMode}
                    responseLanguage={responseLanguage}
                    onUpdate={onUpdate}
                />
            </div>
        )
    }

    return (
        <div className="rounded-lg border p-3">
            <div className="flex items-center gap-2">
                <input
                    type={answerMode === "single" ? "radio" : "checkbox"}
                    name="correct-choice"
                    checked={choice.is_correct}
                    onChange={(event) => onCorrectChange(event.target.checked)}
                    aria-label={t("correct-answer-number", {
                        number: index + 1,
                    })}
                />
                <ChoiceValueField
                    choice={choice}
                    index={index}
                    answerMode={answerMode}
                    responseLanguage={responseLanguage}
                    onUpdate={onUpdate}
                />
                <Input
                    className="w-28"
                    type="number"
                    min={-10000}
                    max={10000}
                    step="0.25"
                    value={choice.points}
                    aria-label={t("answer-points-number", {
                        number: index + 1,
                    })}
                    onChange={(event) =>
                        onUpdate({ points: Number(event.target.value) })
                    }
                    required
                />
                <Button
                    type="button"
                    size="icon"
                    variant="ghost"
                    aria-label={t("remove-choice-number", {
                        number: index + 1,
                    })}
                    disabled={choiceCount <= 2}
                    onClick={onRemove}
                >
                    <Trash2 />
                </Button>
            </div>
            <ChoiceAttachments
                choice={choice}
                index={index}
                onUpdate={onUpdate}
            />
        </div>
    )
}

function ChoiceValueField({
    choice,
    index,
    answerMode,
    responseLanguage,
    onUpdate,
}: {
    choice: EditableChoice
    index: number
    answerMode: AnswerMode
    responseLanguage: CodeLanguage | null
    onUpdate: (update: Partial<EditableChoice>) => void
}) {
    const { t } = useTranslation()
    const hasImage =
        Boolean(choice.image) ||
        Boolean(choice.has_image && !choice.remove_image)
    const hasCode = choice.hasCode && Boolean(choice.codeContent.trim())

    if (answerMode === "written" && responseLanguage) {
        return (
            <div className="min-w-0 flex-1">
                <CodeBlock
                    code={choice.label}
                    language={responseLanguage}
                    editable
                    onCodeChange={(label) => onUpdate({ label })}
                    onCodeKeyDown={(event) =>
                        indentCode(event, choice.label, (label) =>
                            onUpdate({ label })
                        )
                    }
                    editorClassName="min-h-48"
                    maxLength={4000}
                    required
                />
            </div>
        )
    }

    if (answerMode === "written") {
        return (
            <Textarea
                value={choice.label}
                onChange={(event) => onUpdate({ label: event.target.value })}
                maxLength={4000}
                placeholder={t("expected-written-answer-placeholder")}
                required
            />
        )
    }

    return (
        <Input
            value={choice.label}
            onChange={(event) => onUpdate({ label: event.target.value })}
            maxLength={500}
            placeholder={t("choice-placeholder", { number: index + 1 })}
            required={!hasImage && !hasCode}
        />
    )
}

function ChoiceAttachments({
    choice,
    index,
    onUpdate,
}: {
    choice: EditableChoice
    index: number
    onUpdate: (update: Partial<EditableChoice>) => void
}) {
    const { t } = useTranslation()
    const hasImage =
        Boolean(choice.image) ||
        Boolean(choice.has_image && !choice.remove_image)
    const imageInputId = `choice-image-${index}`

    function toggleImage() {
        if (choice.image) {
            onUpdate({ image: undefined, remove_image: false })
            const input = document.getElementById(
                imageInputId
            ) as HTMLInputElement | null
            if (input) input.value = ""
        } else if (choice.has_image && !choice.remove_image) {
            onUpdate({ remove_image: true })
        } else {
            document.getElementById(imageInputId)?.click()
        }
    }

    return (
        <div className="mt-3 space-y-3 border-t pt-3">
            <div className="space-y-2">
                <Input
                    id={imageInputId}
                    type="file"
                    className="hidden"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    onChange={(event) =>
                        onUpdate({
                            image: event.target.files?.[0],
                            remove_image: false,
                        })
                    }
                />
                <Button
                    type="button"
                    variant={hasImage ? "secondary" : "outline"}
                    size="sm"
                    className="w-56 justify-start"
                    onClick={toggleImage}
                >
                    {hasImage ? <Trash2 /> : <ImagePlus />}
                    {t(hasImage ? "remove-image" : "choice-image")}
                </Button>
                {choice.image && (
                    <SelectedImagePreview
                        image={choice.image}
                        alt={t("choice-image")}
                        className="max-h-48 w-full rounded-md border object-contain"
                    />
                )}
            </div>
            <div className="space-y-2">
                <Button
                    type="button"
                    variant={choice.hasCode ? "secondary" : "outline"}
                    size="sm"
                    className="w-56 justify-start"
                    onClick={() => onUpdate({ hasCode: !choice.hasCode })}
                >
                    <Code2 className="size-4" />
                    {t(choice.hasCode ? "remove-code" : "choice-code")}
                </Button>
                {choice.hasCode && (
                    <div className="space-y-2">
                        <select
                            className={NATIVE_SELECT_CLASS_NAME}
                            value={choice.codeLanguage}
                            onChange={(event) =>
                                onUpdate({
                                    codeLanguage: event.target
                                        .value as CodeLanguage,
                                })
                            }
                            aria-label={t("choice-code-language", {
                                number: index + 1,
                            })}
                        >
                            {CODE_LANGUAGES.map((language) => (
                                <option
                                    key={language.value}
                                    value={language.value}
                                >
                                    {language.label}
                                </option>
                            ))}
                        </select>
                        <CodeBlock
                            code={choice.codeContent}
                            language={choice.codeLanguage}
                            runnable
                            editable
                            editorClassName="min-h-28"
                            onCodeChange={(codeContent) =>
                                onUpdate({ codeContent })
                            }
                            onCodeKeyDown={(event) =>
                                indentCode(
                                    event,
                                    choice.codeContent,
                                    (codeContent) => onUpdate({ codeContent })
                                )
                            }
                        />
                    </div>
                )}
            </div>
        </div>
    )
}

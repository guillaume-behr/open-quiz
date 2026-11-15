import type { CodeLanguage, Question } from "@/api/types"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { CodeBlock } from "./code-block"
import { CODE_LANGUAGES } from "./code-languages"
import { indentCode } from "./code-editor-utils"
import { SelectedImagePreview } from "./selected-image-preview"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { RichText } from "@/components/ui/rich-text"
import { Textarea } from "@/components/ui/textarea"
import { hasRichTextFormatting, toggleRichTextMarker } from "@/lib/rich-text"
import {
    Bold,
    Code,
    Code2,
    ImagePlus,
    Italic,
    Trash2,
    type LucideIcon,
} from "lucide-react"
import { useRef, type KeyboardEvent } from "react"
import { useTranslation } from "react-i18next"

const FORMAT_ACTIONS: {
    marker: string
    labelKey: string
    icon: LucideIcon
    shortcut?: string
}[] = [
    { marker: "**", labelKey: "format-bold", icon: Bold, shortcut: "b" },
    { marker: "*", labelKey: "format-italic", icon: Italic, shortcut: "i" },
    { marker: "`", labelKey: "format-code", icon: Code },
]

type QuestionContentFieldsProps = {
    question?: Question
    prompt: string
    image?: File
    removeImage: boolean
    hasCode: boolean
    codeLanguage: CodeLanguage
    codeContent: string
    onPromptChange: (value: string) => void
    onImageChange: (image?: File) => void
    onRemoveImageChange: (remove: boolean) => void
    onHasCodeChange: (hasCode: boolean) => void
    onCodeLanguageChange: (language: CodeLanguage) => void
    onCodeContentChange: (code: string) => void
}

export function QuestionContentFields({
    question,
    prompt,
    image,
    removeImage,
    hasCode,
    codeLanguage,
    codeContent,
    onPromptChange,
    onImageChange,
    onRemoveImageChange,
    onHasCodeChange,
    onCodeLanguageChange,
    onCodeContentChange,
}: QuestionContentFieldsProps) {
    const { t } = useTranslation()
    const promptRef = useRef<HTMLTextAreaElement>(null)
    const hasQuestionImage =
        Boolean(image) || Boolean(question?.has_image && !removeImage)

    function applyFormat(marker: string) {
        const textarea = promptRef.current
        if (!textarea) return
        const next = toggleRichTextMarker(
            {
                value: prompt,
                selectionStart: textarea.selectionStart,
                selectionEnd: textarea.selectionEnd,
            },
            marker
        )
        onPromptChange(next.value)
        // Restore the selection once React has written the new value.
        requestAnimationFrame(() => {
            textarea.focus()
            textarea.setSelectionRange(next.selectionStart, next.selectionEnd)
        })
    }

    function handlePromptKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
        if (!(event.ctrlKey || event.metaKey) || event.altKey) return
        const action = FORMAT_ACTIONS.find(
            ({ shortcut }) => shortcut === event.key.toLowerCase()
        )
        if (!action) return
        event.preventDefault()
        applyFormat(action.marker)
    }

    function toggleImage() {
        if (image) {
            onImageChange(undefined)
            onRemoveImageChange(false)
            const input = document.getElementById(
                "question-image"
            ) as HTMLInputElement | null
            if (input) input.value = ""
        } else if (question?.has_image && !removeImage) {
            onRemoveImageChange(true)
        } else {
            document.getElementById("question-image")?.click()
        }
    }

    return (
        <>
            <Field>
                <div className="flex flex-wrap items-end justify-between gap-2">
                    <FieldLabel htmlFor="question-prompt">
                        {t("question-wording")}
                    </FieldLabel>
                    <div
                        role="toolbar"
                        aria-controls="question-prompt"
                        aria-label={t("format-help")}
                        className="flex gap-1"
                    >
                        {FORMAT_ACTIONS.map(
                            ({ marker, labelKey, icon: Icon, shortcut }) => {
                                const label = t(labelKey)
                                const title = shortcut
                                    ? `${label} (Ctrl+${shortcut.toUpperCase()})`
                                    : label
                                return (
                                    <Button
                                        key={marker}
                                        type="button"
                                        variant="outline"
                                        size="icon-sm"
                                        aria-label={label}
                                        title={title}
                                        // Keep the textarea selection while clicking.
                                        onMouseDown={(event) =>
                                            event.preventDefault()
                                        }
                                        onClick={() => applyFormat(marker)}
                                    >
                                        <Icon />
                                    </Button>
                                )
                            }
                        )}
                    </div>
                </div>
                <Textarea
                    ref={promptRef}
                    id="question-prompt"
                    value={prompt}
                    onChange={(event) => onPromptChange(event.target.value)}
                    onKeyDown={handlePromptKeyDown}
                    aria-describedby="question-prompt-format-help"
                    maxLength={4000}
                    rows={3}
                    required
                />
                <p
                    id="question-prompt-format-help"
                    className="text-xs text-muted-foreground"
                >
                    {t("format-help")}
                </p>
                {hasRichTextFormatting(prompt) && (
                    <div className="rounded-lg border bg-muted/30 p-3">
                        <p className="text-xs font-semibold text-muted-foreground">
                            {t("format-preview")}
                        </p>
                        <p className="mt-1 text-base font-medium">
                            <RichText text={prompt} />
                        </p>
                    </div>
                )}
            </Field>
            <Field>
                <Input
                    id="question-image"
                    type="file"
                    className="hidden"
                    accept="image/jpeg,image/png,image/webp,image/gif"
                    onChange={(event) => {
                        const selectedImage = event.target.files?.[0]
                        onImageChange(selectedImage)
                        if (selectedImage) onRemoveImageChange(false)
                    }}
                />
                <Button
                    type="button"
                    variant={hasQuestionImage ? "secondary" : "outline"}
                    className="w-fit"
                    onClick={toggleImage}
                >
                    {hasQuestionImage ? <Trash2 /> : <ImagePlus />}
                    {t(hasQuestionImage ? "remove-image" : "question-image")}
                </Button>
                {image && (
                    <SelectedImagePreview
                        image={image}
                        alt={t("question-image")}
                        className="max-h-64 w-full rounded-lg border object-contain"
                    />
                )}
            </Field>
            <Field>
                <Button
                    type="button"
                    variant={hasCode ? "secondary" : "outline"}
                    className="w-fit"
                    onClick={() => onHasCodeChange(!hasCode)}
                >
                    <Code2 className="size-4" />
                    {t(hasCode ? "remove-code" : "include-code")}
                </Button>
                {hasCode && (
                    <div className="mt-2 space-y-3">
                        <div className="max-w-xs">
                            <FieldLabel htmlFor="question-code-language">
                                {t("code-language")}
                            </FieldLabel>
                            <select
                                id="question-code-language"
                                className={NATIVE_SELECT_CLASS_NAME}
                                value={codeLanguage}
                                onChange={(event) =>
                                    onCodeLanguageChange(
                                        event.target.value as CodeLanguage
                                    )
                                }
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
                        </div>
                        <CodeBlock
                            code={codeContent}
                            language={codeLanguage}
                            runnable
                            editable
                            onCodeChange={onCodeContentChange}
                            onCodeKeyDown={(event) =>
                                indentCode(
                                    event,
                                    codeContent,
                                    onCodeContentChange
                                )
                            }
                        />
                    </div>
                )}
            </Field>
        </>
    )
}

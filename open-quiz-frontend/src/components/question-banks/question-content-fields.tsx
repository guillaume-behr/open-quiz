import type { CodeLanguage, Question } from "@/api/types"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { CodeBlock } from "./code-block"
import { CODE_LANGUAGES } from "./code-languages"
import { indentCode } from "./code-editor-utils"
import { SelectedImagePreview } from "./selected-image-preview"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Code2, ImagePlus, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"

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
    const hasQuestionImage =
        Boolean(image) || Boolean(question?.has_image && !removeImage)

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
                <FieldLabel htmlFor="question-prompt">
                    {t("question-wording")}
                </FieldLabel>
                <Textarea
                    id="question-prompt"
                    value={prompt}
                    onChange={(event) => onPromptChange(event.target.value)}
                    maxLength={4000}
                    rows={3}
                    required
                />
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

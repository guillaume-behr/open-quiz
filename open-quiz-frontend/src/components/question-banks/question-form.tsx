import { ApiError } from "@/api/client"
import { createQuestion, updateQuestion } from "@/api/question-banks"
import type {
    AnswerMode,
    CodeLanguage,
    EncodedImage,
    NewQuestion,
    Question,
    QuestionDifficulty,
} from "@/api/types"
import { Button } from "@/components/ui/button"
import { FieldError, FieldGroup } from "@/components/ui/field"
import { LoaderCircle } from "lucide-react"
import { type FormEvent, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { QuestionChoicesEditor } from "./question-choices-editor"
import { QuestionContentFields } from "./question-content-fields"
import type { EditableChoice } from "./question-form-types"
import { QuestionSettingsFields } from "./question-settings-fields"

type QuestionFormProps = {
    questionBankId: number
    question?: Question
    onSaved: (question: Question) => void
    onCancel: () => void
}

const ALLOWED_IMAGE_TYPES: ReadonlySet<string> = new Set([
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
])

function encodeImage(file: File): Promise<EncodedImage> {
    return new Promise((resolve, reject) => {
        if (!ALLOWED_IMAGE_TYPES.has(file.type)) {
            reject(new Error("Unsupported image type"))
            return
        }
        const contentType = file.type as EncodedImage["content_type"]
        const reader = new FileReader()
        reader.onerror = () => reject(reader.error)
        reader.onload = () => {
            const result = String(reader.result)
            const separatorIndex = result.indexOf(",")
            if (separatorIndex < 0) {
                reject(new Error("Invalid image"))
                return
            }
            resolve({
                content_type: contentType,
                data_base64: result.slice(separatorIndex + 1),
            })
        }
        reader.readAsDataURL(file)
    })
}

function initialChoices(question?: Question): EditableChoice[] {
    return (
        question?.choices.map((choice) => ({
            id: choice.id,
            label: choice.label,
            is_correct: choice.is_correct,
            points: choice.points,
            has_image: choice.has_image,
            remove_image: false,
            hasCode: Boolean(choice.code_content),
            codeLanguage: choice.code_language ?? "javascript",
            codeContent: choice.code_content ?? "",
        })) ?? [createEmptyChoice(true), createEmptyChoice(false)]
    )
}

function createEmptyChoice(isCorrect: boolean): EditableChoice {
    return {
        label: "",
        is_correct: isCorrect,
        points: isCorrect ? 1 : 0,
        has_image: false,
        remove_image: false,
        hasCode: false,
        codeLanguage: "javascript",
        codeContent: "",
    }
}

export function QuestionForm({
    questionBankId,
    question,
    onSaved,
    onCancel,
}: QuestionFormProps) {
    const { t } = useTranslation()
    const [prompt, setPrompt] = useState(question?.prompt ?? "")
    const [points] = useState(question?.points ?? 1)
    const [difficulty, setDifficulty] = useState<QuestionDifficulty>(
        question?.difficulty ?? "medium"
    )
    const [answerMode, setAnswerMode] = useState<AnswerMode>(
        question?.answer_mode ?? "single"
    )
    const [answerModeDisclosed, setAnswerModeDisclosed] = useState(
        question?.answer_mode_disclosed ?? true
    )
    const [responseLanguage, setResponseLanguage] =
        useState<CodeLanguage | null>(question?.response_language ?? null)
    const [choices, setChoices] = useState<EditableChoice[]>(() =>
        initialChoices(question)
    )
    const choiceModeBackup = useRef<EditableChoice[] | null>(null)
    const answerModeDisclosedBackup = useRef<boolean | null>(null)
    const [image, setImage] = useState<File | undefined>()
    const [removeImage, setRemoveImage] = useState(false)
    const [hasCode, setHasCode] = useState(Boolean(question?.code_content))
    const [codeLanguage, setCodeLanguage] = useState<CodeLanguage>(
        question?.code_language ?? "javascript"
    )
    const [codeContent, setCodeContent] = useState(question?.code_content ?? "")
    const [isCreating, setIsCreating] = useState(false)
    const [error, setError] = useState<string | null>(null)

    function selectCorrectChoice(index: number, checked: boolean): void {
        setChoices((current) => {
            return current.map((choice, choiceIndex) => {
                if (answerMode === "single") {
                    const isSelected = choiceIndex === index
                    return {
                        ...choice,
                        is_correct: isSelected,
                    }
                }
                if (choiceIndex !== index) return choice
                return {
                    ...choice,
                    is_correct: checked,
                }
            })
        })
    }

    function changeAnswerMode(mode: AnswerMode): void {
        const previousMode = answerMode
        setAnswerMode(mode)

        if (mode === "written") {
            if (previousMode !== "written") {
                choiceModeBackup.current = choices
                answerModeDisclosedBackup.current = answerModeDisclosed
            }
            setAnswerModeDisclosed(true)
            setChoices((current) => [
                {
                    ...current[0],
                    is_correct: true,
                    image: undefined,
                    has_image: false,
                    remove_image: true,
                    hasCode: false,
                    codeContent: "",
                },
            ])
            return
        }

        if (previousMode === "written") {
            setAnswerModeDisclosed(
                answerModeDisclosedBackup.current ?? answerModeDisclosed
            )
            const restoredChoices = choiceModeBackup.current ?? [
                createEmptyChoice(true),
                createEmptyChoice(false),
            ]
            choiceModeBackup.current = null
            answerModeDisclosedBackup.current = null
            setChoices(
                mode === "single"
                    ? restoredChoices.map((choice, index) => ({
                          ...choice,
                          is_correct: index === 0,
                      }))
                    : restoredChoices
            )
            return
        }

        if (mode === "single") {
            const firstCorrectIndex = choices.findIndex(
                (choice) => choice.is_correct
            )
            setChoices((current) =>
                current.map((choice, index) => ({
                    ...choice,
                    is_correct: index === Math.max(0, firstCorrectIndex),
                }))
            )
        }
    }

    function removeChoice(index: number): void {
        setChoices((current) => {
            const remaining = current.filter(
                (_, choiceIndex) => choiceIndex !== index
            )
            if (!remaining.some((choice) => choice.is_correct)) {
                return remaining.map((choice, choiceIndex) => ({
                    ...choice,
                    is_correct: choiceIndex === 0,
                }))
            }
            return remaining
        })
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setError(null)
        setIsCreating(true)

        try {
            const encodedChoices = await Promise.all(
                choices.map(async (choice) => ({
                    id: choice.id,
                    label: choice.label.trim(),
                    is_correct: choice.is_correct,
                    points: choice.points,
                    image: choice.image
                        ? await encodeImage(choice.image)
                        : null,
                    remove_image: choice.remove_image,
                    code_language: choice.hasCode ? choice.codeLanguage : null,
                    code_content: choice.hasCode ? choice.codeContent : null,
                }))
            )
            const payload: NewQuestion = {
                prompt: prompt.trim(),
                points,
                difficulty,
                answer_mode: answerMode,
                answer_mode_disclosed: answerModeDisclosed,
                response_language:
                    answerMode === "written" ? responseLanguage : null,
                code_language: hasCode ? codeLanguage : null,
                code_content: hasCode ? codeContent : null,
                choices: encodedChoices,
            }
            const savedQuestion = question
                ? await updateQuestion(
                      question.id,
                      { ...payload, remove_image: removeImage },
                      image
                  )
                : await createQuestion(questionBankId, payload, image)
            onSaved(savedQuestion)
        } catch (caughtError) {
            setError(
                caughtError instanceof ApiError && caughtError.status === 413
                    ? t("question-image-too-large")
                    : t("question-save-error")
            )
        } finally {
            setIsCreating(false)
        }
    }

    return (
        <form onSubmit={handleSubmit}>
            <FieldGroup className="gap-4">
                <QuestionContentFields
                    question={question}
                    prompt={prompt}
                    image={image}
                    removeImage={removeImage}
                    hasCode={hasCode}
                    codeLanguage={codeLanguage}
                    codeContent={codeContent}
                    onPromptChange={setPrompt}
                    onImageChange={setImage}
                    onRemoveImageChange={setRemoveImage}
                    onHasCodeChange={setHasCode}
                    onCodeLanguageChange={setCodeLanguage}
                    onCodeContentChange={setCodeContent}
                />
                <QuestionSettingsFields
                    difficulty={difficulty}
                    answerMode={answerMode}
                    answerModeDisclosed={answerModeDisclosed}
                    responseLanguage={responseLanguage}
                    onDifficultyChange={setDifficulty}
                    onAnswerModeChange={changeAnswerMode}
                    onAnswerModeDisclosedChange={setAnswerModeDisclosed}
                    onResponseLanguageChange={setResponseLanguage}
                />
                <QuestionChoicesEditor
                    choices={choices}
                    answerMode={answerMode}
                    responseLanguage={responseLanguage}
                    onChoicesChange={setChoices}
                    onCorrectChoiceChange={selectCorrectChoice}
                    onRemoveChoice={removeChoice}
                />
                {error && <FieldError>{error}</FieldError>}
                <div className="flex justify-end gap-2 border-t pt-4">
                    <Button type="button" variant="outline" onClick={onCancel}>
                        {t("cancel")}
                    </Button>
                    <Button type="submit" disabled={isCreating}>
                        {isCreating && (
                            <LoaderCircle className="animate-spin" />
                        )}
                        {isCreating
                            ? t("creating-question")
                            : t(question ? "update-question" : "save-question")}
                    </Button>
                </div>
            </FieldGroup>
        </form>
    )
}

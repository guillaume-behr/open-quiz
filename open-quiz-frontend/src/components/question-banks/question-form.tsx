import {
    createQuestion,
    updateQuestion,
    ApiError,
    type AnswerMode,
    type CorrectionMode,
    type CodeLanguage,
    type EncodedImage,
    type NewQuestion,
    type Question,
    type QuestionDifficulty,
} from "@/api/api"
import { CodeBlock } from "@/components/question-banks/code-block"
import { CODE_LANGUAGES } from "@/components/question-banks/code-languages"
import { Button } from "@/components/ui/button"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Textarea } from "@/components/ui/textarea"
import { Code2, ImagePlus, LoaderCircle, Plus, Trash2 } from "lucide-react"
import {
    type FormEvent,
    type KeyboardEvent,
    useEffect,
    useMemo,
    useState,
} from "react"
import { useTranslation } from "react-i18next"

type EditableChoice = {
    id?: number
    label: string
    is_correct: boolean
    points: number
    has_image: boolean
    image?: File
    remove_image: boolean
    hasCode: boolean
    codeLanguage: CodeLanguage
    codeContent: string
}

type QuestionFormProps = {
    questionBankId: number
    question?: Question
    onSaved: (question: Question) => void
    onCancel: () => void
}

const selectClassName =
    "h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

function encodeImage(file: File): Promise<EncodedImage> {
    return new Promise((resolve, reject) => {
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
                content_type: file.type as EncodedImage["content_type"],
                data_base64: result.slice(separatorIndex + 1),
            })
        }
        reader.readAsDataURL(file)
    })
}

function SelectedImagePreview({
    image,
    alt,
    className,
}: {
    image: File
    alt: string
    className: string
}) {
    const imageUrl = useMemo(() => URL.createObjectURL(image), [image])

    useEffect(() => {
        return () => URL.revokeObjectURL(imageUrl)
    }, [imageUrl])

    return <img src={imageUrl} alt={alt} className={className} />
}

function indentCode(
    event: KeyboardEvent<HTMLTextAreaElement>,
    value: string,
    onChange: (value: string) => void
): void {
    if (event.key !== "Tab") return

    event.preventDefault()
    const textarea = event.currentTarget
    const start = textarea.selectionStart
    const end = textarea.selectionEnd
    const lineStart = value.lastIndexOf("\n", start - 1) + 1

    if (start !== end) {
        const selectedCode = value.slice(lineStart, end)
        const indentedCode = selectedCode.replace(/^/gm, "\t")
        onChange(value.slice(0, lineStart) + indentedCode + value.slice(end))
        requestAnimationFrame(() => {
            textarea.setSelectionRange(
                start + 1,
                end + (indentedCode.length - selectedCode.length)
            )
        })
        return
    }

    onChange(value.slice(0, start) + "\t" + value.slice(end))
    requestAnimationFrame(() => {
        textarea.setSelectionRange(start + 1, start + 1)
    })
}

export function QuestionForm({
    questionBankId,
    question,
    onSaved,
    onCancel,
}: QuestionFormProps) {
    const { t } = useTranslation()
    const [prompt, setPrompt] = useState(question?.prompt ?? "")
    const [difficulty, setDifficulty] = useState<QuestionDifficulty>(
        question?.difficulty ?? "medium"
    )
    const [answerMode, setAnswerMode] = useState<AnswerMode>(
        question?.answer_mode ?? "single"
    )
    const [answerModeDisclosed, setAnswerModeDisclosed] = useState(
        question?.answer_mode_disclosed ?? true
    )
    const [correctionMode, setCorrectionMode] = useState<CorrectionMode>(
        question?.correction_mode ?? "automatic"
    )
    const [choices, setChoices] = useState<EditableChoice[]>(
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
        })) ?? [
            {
                label: "",
                is_correct: true,
                points: 1,
                has_image: false,
                remove_image: false,
                hasCode: false,
                codeLanguage: "javascript",
                codeContent: "",
            },
            {
                label: "",
                is_correct: false,
                points: 0,
                has_image: false,
                remove_image: false,
                hasCode: false,
                codeLanguage: "javascript",
                codeContent: "",
            },
        ]
    )
    const [image, setImage] = useState<File | undefined>()
    const [removeImage, setRemoveImage] = useState(false)
    const [hasCode, setHasCode] = useState(Boolean(question?.code_content))
    const [codeLanguage, setCodeLanguage] = useState<CodeLanguage>(
        question?.code_language ?? "javascript"
    )
    const [codeContent, setCodeContent] = useState(question?.code_content ?? "")
    const [isCreating, setIsCreating] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const hasQuestionImage =
        Boolean(image) || Boolean(question?.has_image && !removeImage)

    function updateChoice(
        index: number,
        update: Partial<EditableChoice>
    ): void {
        setChoices((current) =>
            current.map((choice, choiceIndex) =>
                choiceIndex === index ? { ...choice, ...update } : choice
            )
        )
    }

    function selectCorrectChoice(index: number, checked: boolean): void {
        setChoices((current) => {
            const previousPoints =
                current.find((choice) => choice.is_correct)?.points ?? 1
            return current.map((choice, choiceIndex) => {
                if (answerMode === "single") {
                    const isSelected = choiceIndex === index
                    return {
                        ...choice,
                        is_correct: isSelected,
                        points: isSelected
                            ? Math.max(0, choice.points || previousPoints || 1)
                            : 0,
                    }
                }
                if (choiceIndex !== index) return choice
                return {
                    ...choice,
                    is_correct: checked,
                    points: checked ? Math.max(0, choice.points || 1) : 0,
                }
            })
        })
    }

    function changeAnswerMode(mode: AnswerMode): void {
        setAnswerMode(mode)
        if (mode === "single" && correctionMode === "automatic") {
            const firstCorrectIndex = choices.findIndex(
                (choice) => choice.is_correct
            )
            setChoices((current) =>
                current.map((choice, index) => ({
                    ...choice,
                    is_correct: index === Math.max(0, firstCorrectIndex),
                    points:
                        index === Math.max(0, firstCorrectIndex)
                            ? Math.max(0, choice.points || 1)
                            : 0,
                }))
            )
        }
    }

    function changeCorrectionMode(mode: CorrectionMode): void {
        setCorrectionMode(mode)
        setChoices((current) => {
            if (mode === "manual") {
                return current.map((choice) => ({
                    ...choice,
                    is_correct: false,
                }))
            }
            const hasCorrectChoice = current.some((choice) => choice.is_correct)
            return current.map((choice, index) => {
                const isCorrect =
                    choice.is_correct || (index === 0 && !hasCorrectChoice)
                return {
                    ...choice,
                    is_correct: isCorrect,
                    points: isCorrect ? Math.max(0, choice.points || 1) : 0,
                }
            })
        })
    }

    function removeChoice(index: number): void {
        setChoices((current) => {
            const remaining = current.filter(
                (_, choiceIndex) => choiceIndex !== index
            )
            if (
                correctionMode === "automatic" &&
                !remaining.some((choice) => choice.is_correct)
            ) {
                return remaining.map((choice, choiceIndex) => ({
                    ...choice,
                    is_correct: choiceIndex === 0,
                    points:
                        choiceIndex === 0 ? Math.max(0, choice.points || 1) : 0,
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
                difficulty,
                answer_mode: answerMode,
                answer_mode_disclosed: answerModeDisclosed,
                correction_mode: correctionMode,
                code_language: hasCode ? codeLanguage : null,
                code_content: hasCode ? codeContent : null,
                choices: encodedChoices,
            }
            const savedQuestion = question
                ? await updateQuestion(
                      question.id,
                      {
                          ...payload,
                          remove_image: removeImage,
                      },
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
                <Field>
                    <FieldLabel htmlFor="question-prompt">
                        {t("question-wording")}
                    </FieldLabel>
                    <Textarea
                        id="question-prompt"
                        value={prompt}
                        onChange={(event) => setPrompt(event.target.value)}
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
                            setImage(selectedImage)
                            if (selectedImage) {
                                setRemoveImage(false)
                            }
                        }}
                    />
                    <Button
                        type="button"
                        variant={hasQuestionImage ? "secondary" : "outline"}
                        className="w-fit"
                        onClick={() => {
                            if (image) {
                                setImage(undefined)
                                setRemoveImage(false)
                                const input = document.getElementById(
                                    "question-image"
                                ) as HTMLInputElement | null
                                if (input) input.value = ""
                            } else if (question?.has_image && !removeImage) {
                                setRemoveImage(true)
                            } else {
                                document
                                    .getElementById("question-image")
                                    ?.click()
                            }
                        }}
                    >
                        {hasQuestionImage ? <Trash2 /> : <ImagePlus />}
                        {t(
                            hasQuestionImage ? "remove-image" : "question-image"
                        )}
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
                        onClick={() => setHasCode((current) => !current)}
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
                                    className={selectClassName}
                                    value={codeLanguage}
                                    onChange={(event) =>
                                        setCodeLanguage(
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
                                onCodeChange={setCodeContent}
                                onCodeKeyDown={(event) =>
                                    indentCode(
                                        event,
                                        codeContent,
                                        setCodeContent
                                    )
                                }
                            />
                        </div>
                    )}
                </Field>

                <div className="grid gap-4 sm:grid-cols-3">
                    <Field>
                        <FieldLabel htmlFor="question-difficulty">
                            {t("difficulty")}
                        </FieldLabel>
                        <select
                            id="question-difficulty"
                            className={selectClassName}
                            value={difficulty}
                            onChange={(event) =>
                                setDifficulty(
                                    event.target.value as QuestionDifficulty
                                )
                            }
                        >
                            <option value="easy">{t("difficulty-easy")}</option>
                            <option value="medium">
                                {t("difficulty-medium")}
                            </option>
                            <option value="hard">{t("difficulty-hard")}</option>
                        </select>
                    </Field>
                    <Field>
                        <FieldLabel htmlFor="question-answer-mode">
                            {t("answer-mode")}
                        </FieldLabel>
                        <select
                            id="question-answer-mode"
                            className={selectClassName}
                            value={answerMode}
                            onChange={(event) =>
                                changeAnswerMode(
                                    event.target.value as AnswerMode
                                )
                            }
                        >
                            <option value="single">{t("single-choice")}</option>
                            <option value="multiple">
                                {t("multiple-choice")}
                            </option>
                        </select>
                    </Field>
                    <Field>
                        <FieldLabel htmlFor="question-correction-mode">
                            {t("correction-mode")}
                        </FieldLabel>
                        <select
                            id="question-correction-mode"
                            className={selectClassName}
                            value={correctionMode}
                            onChange={(event) =>
                                changeCorrectionMode(
                                    event.target.value as CorrectionMode
                                )
                            }
                        >
                            <option value="automatic">
                                {t("automatic-correction")}
                            </option>
                            <option value="manual">
                                {t("manual-correction")}
                            </option>
                        </select>
                    </Field>
                </div>

                <label className="flex items-center gap-2 text-sm">
                    <input
                        type="checkbox"
                        checked={answerModeDisclosed}
                        onChange={(event) =>
                            setAnswerModeDisclosed(event.target.checked)
                        }
                    />
                    {t("disclose-answer-mode")}
                </label>

                <Field>
                    <FieldLabel>{t("answer-choices")}</FieldLabel>
                    <div className="space-y-2">
                        {choices.map((choice, index) => (
                            <div
                                key={choice.id ?? index}
                                className="rounded-lg border p-3"
                            >
                                <div className="flex items-center gap-2">
                                    {correctionMode === "automatic" ? (
                                        <input
                                            type={
                                                answerMode === "single"
                                                    ? "radio"
                                                    : "checkbox"
                                            }
                                            name="correct-choice"
                                            checked={choice.is_correct}
                                            onChange={(event) =>
                                                selectCorrectChoice(
                                                    index,
                                                    event.target.checked
                                                )
                                            }
                                            aria-label={t(
                                                "correct-answer-number",
                                                {
                                                    number: index + 1,
                                                }
                                            )}
                                        />
                                    ) : (
                                        <span
                                            className="text-muted-foreground"
                                            aria-hidden="true"
                                        >
                                            ○
                                        </span>
                                    )}
                                    <Input
                                        value={choice.label}
                                        onChange={(event) =>
                                            updateChoice(index, {
                                                label: event.target.value,
                                            })
                                        }
                                        maxLength={500}
                                        placeholder={t("choice-placeholder", {
                                            number: index + 1,
                                        })}
                                        required
                                    />
                                    <div className="flex shrink-0 items-center gap-1">
                                        <Input
                                            type="number"
                                            className="w-20"
                                            value={choice.points}
                                            min={choice.is_correct ? 0 : -1000}
                                            max={1000}
                                            step="0.25"
                                            onChange={(event) =>
                                                updateChoice(index, {
                                                    points: choice.is_correct
                                                        ? Math.max(
                                                              0,
                                                              Number(
                                                                  event.target
                                                                      .value
                                                              )
                                                          )
                                                        : Math.min(
                                                              0,
                                                              Number(
                                                                  event.target
                                                                      .value
                                                              )
                                                          ),
                                                })
                                            }
                                            aria-label={t(
                                                "answer-points-number",
                                                {
                                                    number: index + 1,
                                                }
                                            )}
                                            required
                                        />
                                        <span className="text-xs text-muted-foreground">
                                            {t("points-short")}
                                        </span>
                                    </div>
                                    <Button
                                        type="button"
                                        size="icon"
                                        variant="ghost"
                                        aria-label={t("remove-choice-number", {
                                            number: index + 1,
                                        })}
                                        disabled={choices.length <= 2}
                                        onClick={() => removeChoice(index)}
                                    >
                                        <Trash2 />
                                    </Button>
                                </div>
                                <div className="mt-3 space-y-3 border-t pt-3">
                                    <div className="space-y-2">
                                        <Input
                                            id={`choice-image-${index}`}
                                            type="file"
                                            className="hidden"
                                            accept="image/jpeg,image/png,image/webp,image/gif"
                                            onChange={(event) => {
                                                const selectedImage =
                                                    event.target.files?.[0]
                                                updateChoice(index, {
                                                    image: selectedImage,
                                                    remove_image: false,
                                                })
                                            }}
                                        />
                                        <Button
                                            type="button"
                                            variant={
                                                choice.image ||
                                                (choice.has_image &&
                                                    !choice.remove_image)
                                                    ? "secondary"
                                                    : "outline"
                                            }
                                            size="sm"
                                            className="w-56 justify-start"
                                            onClick={() => {
                                                if (choice.image) {
                                                    updateChoice(index, {
                                                        image: undefined,
                                                        remove_image: false,
                                                    })
                                                    const input =
                                                        document.getElementById(
                                                            `choice-image-${index}`
                                                        ) as HTMLInputElement | null
                                                    if (input) input.value = ""
                                                } else if (
                                                    choice.has_image &&
                                                    !choice.remove_image
                                                ) {
                                                    updateChoice(index, {
                                                        remove_image: true,
                                                    })
                                                } else {
                                                    document
                                                        .getElementById(
                                                            `choice-image-${index}`
                                                        )
                                                        ?.click()
                                                }
                                            }}
                                        >
                                            {choice.image ||
                                            (choice.has_image &&
                                                !choice.remove_image) ? (
                                                <Trash2 />
                                            ) : (
                                                <ImagePlus />
                                            )}
                                            {t(
                                                choice.image ||
                                                    (choice.has_image &&
                                                        !choice.remove_image)
                                                    ? "remove-image"
                                                    : "choice-image"
                                            )}
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
                                            variant={
                                                choice.hasCode
                                                    ? "secondary"
                                                    : "outline"
                                            }
                                            size="sm"
                                            className="w-56 justify-start"
                                            onClick={() =>
                                                updateChoice(index, {
                                                    hasCode: !choice.hasCode,
                                                })
                                            }
                                        >
                                            <Code2 className="size-4" />
                                            {t(
                                                choice.hasCode
                                                    ? "remove-code"
                                                    : "choice-code"
                                            )}
                                        </Button>
                                        {choice.hasCode && (
                                            <div className="space-y-2">
                                                <select
                                                    className={selectClassName}
                                                    value={choice.codeLanguage}
                                                    onChange={(event) =>
                                                        updateChoice(index, {
                                                            codeLanguage: event
                                                                .target
                                                                .value as CodeLanguage,
                                                        })
                                                    }
                                                    aria-label={t(
                                                        "choice-code-language",
                                                        {
                                                            number: index + 1,
                                                        }
                                                    )}
                                                >
                                                    {CODE_LANGUAGES.map(
                                                        (language) => (
                                                            <option
                                                                key={
                                                                    language.value
                                                                }
                                                                value={
                                                                    language.value
                                                                }
                                                            >
                                                                {language.label}
                                                            </option>
                                                        )
                                                    )}
                                                </select>
                                                <CodeBlock
                                                    code={choice.codeContent}
                                                    language={
                                                        choice.codeLanguage
                                                    }
                                                    runnable
                                                    editable
                                                    editorClassName="min-h-28"
                                                    onCodeChange={(
                                                        codeContent
                                                    ) =>
                                                        updateChoice(index, {
                                                            codeContent,
                                                        })
                                                    }
                                                    onCodeKeyDown={(event) =>
                                                        indentCode(
                                                            event,
                                                            choice.codeContent,
                                                            (codeContent) =>
                                                                updateChoice(
                                                                    index,
                                                                    {
                                                                        codeContent,
                                                                    }
                                                                )
                                                        )
                                                    }
                                                />
                                            </div>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                    <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        className="mt-2 w-fit"
                        disabled={choices.length >= 12}
                        onClick={() =>
                            setChoices((current) => [
                                ...current,
                                {
                                    label: "",
                                    is_correct: false,
                                    points: 0,
                                    has_image: false,
                                    remove_image: false,
                                    hasCode: false,
                                    codeLanguage: "javascript",
                                    codeContent: "",
                                },
                            ])
                        }
                    >
                        <Plus />
                        {t("add-choice")}
                    </Button>
                    {correctionMode === "manual" && (
                        <p className="text-xs text-muted-foreground">
                            {t("manual-correction-help")}
                        </p>
                    )}
                </Field>

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

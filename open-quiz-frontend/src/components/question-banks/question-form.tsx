import {
    createQuestion,
    updateQuestion,
    type AnswerMode,
    type CorrectionMode,
    type CodeLanguage,
    type NewQuestion,
    type Question,
    type QuestionDifficulty,
} from "@/api/api"
import {
    CodeBlock,
} from "@/components/question-banks/code-block"
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
import { type FormEvent, useState } from "react"
import { useTranslation } from "react-i18next"

type EditableChoice = {
    label: string
    is_correct: boolean
}

type QuestionFormProps = {
    questionBankId: number
    question?: Question
    onSaved: (question: Question) => void
    onCancel: () => void
}

const selectClassName =
    "h-9 w-full rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"

export function QuestionForm({
    questionBankId,
    question,
    onSaved,
    onCancel,
}: QuestionFormProps) {
    const { t } = useTranslation()
    const [prompt, setPrompt] = useState(question?.prompt ?? "")
    const [difficulty, setDifficulty] =
        useState<QuestionDifficulty>(question?.difficulty ?? "medium")
    const [answerMode, setAnswerMode] = useState<AnswerMode>(
        question?.answer_mode ?? "single"
    )
    const [answerModeDisclosed, setAnswerModeDisclosed] = useState(
        question?.answer_mode_disclosed ?? true
    )
    const [correctionMode, setCorrectionMode] =
        useState<CorrectionMode>(question?.correction_mode ?? "automatic")
    const [choices, setChoices] = useState<EditableChoice[]>(
        question?.choices.map((choice) => ({
            label: choice.label,
            is_correct: choice.is_correct,
        })) ?? [
            { label: "", is_correct: true },
            { label: "", is_correct: false },
        ]
    )
    const [image, setImage] = useState<File | undefined>()
    const [removeImage, setRemoveImage] = useState(false)
    const [hasCode, setHasCode] = useState(Boolean(question?.code_content))
    const [codeLanguage, setCodeLanguage] =
        useState<CodeLanguage>(question?.code_language ?? "javascript")
    const [codeContent, setCodeContent] = useState(
        question?.code_content ?? ""
    )
    const [isCreating, setIsCreating] = useState(false)
    const [error, setError] = useState<string | null>(null)

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
        setChoices((current) =>
            current.map((choice, choiceIndex) => ({
                ...choice,
                is_correct:
                    answerMode === "single"
                        ? choiceIndex === index && checked
                        : choiceIndex === index
                          ? checked
                          : choice.is_correct,
            }))
        )
    }

    function changeAnswerMode(mode: AnswerMode): void {
        setAnswerMode(mode)
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

    function changeCorrectionMode(mode: CorrectionMode): void {
        setCorrectionMode(mode)
        setChoices((current) =>
            current.map((choice, index) => ({
                ...choice,
                is_correct:
                    mode === "automatic"
                        ? choice.is_correct ||
                          (index === 0 &&
                              !current.some((item) => item.is_correct))
                        : false,
            }))
        )
    }

    async function handleSubmit(event: FormEvent<HTMLFormElement>) {
        event.preventDefault()
        setError(null)
        setIsCreating(true)

        const payload: NewQuestion = {
            prompt: prompt.trim(),
            difficulty,
            answer_mode: answerMode,
            answer_mode_disclosed: answerModeDisclosed,
            correction_mode: correctionMode,
            code_language: hasCode ? codeLanguage : null,
            code_content: hasCode ? codeContent : null,
            choices: choices.map((choice) => ({
                label: choice.label.trim(),
                is_correct: choice.is_correct,
            })),
        }

        try {
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
        } catch {
            setError(t("question-create-error"))
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
                            <option value="single">
                                {t("single-choice")}
                            </option>
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
                                key={index}
                                className="flex items-center gap-2"
                            >
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
                                        aria-label={t("correct-answer")}
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
                                <Button
                                    type="button"
                                    size="icon"
                                    variant="ghost"
                                    aria-label={t("remove-choice")}
                                    disabled={choices.length <= 2}
                                    onClick={() =>
                                        setChoices((current) =>
                                            current.filter(
                                                (_, choiceIndex) =>
                                                    choiceIndex !== index
                                            )
                                        )
                                    }
                                >
                                    <Trash2 />
                                </Button>
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
                                { label: "", is_correct: false },
                            ])
                        }
                    >
                        <Plus />
                        {t("add-choice")}
                    </Button>
                    <p className="text-xs text-muted-foreground">
                        {correctionMode === "automatic"
                            ? t("select-correct-answers")
                            : t("manual-correction-help")}
                    </p>
                </Field>

                <Field>
                    <FieldLabel htmlFor="question-image">
                        <ImagePlus />
                        {t("question-image")}
                    </FieldLabel>
                    <Input
                        id="question-image"
                        type="file"
                        accept="image/jpeg,image/png,image/webp,image/gif"
                        onChange={(event) => {
                            const selectedImage = event.target.files?.[0]
                            setImage(selectedImage)
                            if (selectedImage) {
                                setRemoveImage(false)
                            }
                        }}
                    />
                    {question?.has_image && !image && (
                        <label className="flex items-center gap-2 text-sm text-muted-foreground">
                            <input
                                type="checkbox"
                                checked={removeImage}
                                onChange={(event) =>
                                    setRemoveImage(event.target.checked)
                                }
                            />
                            {t("remove-current-image")}
                        </label>
                    )}
                    <p className="text-xs text-muted-foreground">
                        {t("question-image-help")}
                    </p>
                </Field>

                <Field>
                    <label className="flex items-center gap-2 text-sm font-medium">
                        <input
                            type="checkbox"
                            checked={hasCode}
                            onChange={(event) =>
                                setHasCode(event.target.checked)
                            }
                        />
                        <Code2 className="size-4" />
                        {t("include-code")}
                    </label>
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
                                            event.target
                                                .value as CodeLanguage
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
                            <div>
                                <FieldLabel htmlFor="question-code">
                                    {t("source-code")}
                                </FieldLabel>
                                <Textarea
                                    id="question-code"
                                    className="min-h-40 font-mono text-sm whitespace-pre"
                                    value={codeContent}
                                    onChange={(event) =>
                                        setCodeContent(event.target.value)
                                    }
                                    maxLength={20000}
                                    spellCheck={false}
                                    required
                                />
                            </div>
                            {codeContent.trim() && (
                                <div>
                                    <p className="mb-2 text-sm font-medium">
                                        {t("code-preview")}
                                    </p>
                                    <CodeBlock
                                        code={codeContent}
                                        language={codeLanguage}
                                    />
                                </div>
                            )}
                        </div>
                    )}
                </Field>

                {error && <FieldError>{error}</FieldError>}
                <div className="flex justify-end gap-2 border-t pt-4">
                    <Button
                        type="button"
                        variant="outline"
                        onClick={onCancel}
                    >
                        {t("cancel")}
                    </Button>
                    <Button type="submit" disabled={isCreating}>
                        {isCreating && (
                            <LoaderCircle className="animate-spin" />
                        )}
                        {isCreating
                            ? t("creating-question")
                            : t(
                                  question
                                      ? "update-question"
                                      : "save-question"
                              )}
                    </Button>
                </div>
            </FieldGroup>
        </form>
    )
}

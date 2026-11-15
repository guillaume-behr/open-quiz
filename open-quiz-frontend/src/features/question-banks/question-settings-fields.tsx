import type { AnswerMode, CodeLanguage, QuestionDifficulty } from "@/api/types"
import { NATIVE_SELECT_CLASS_NAME } from "@/components/ui/native-select"
import { CODE_LANGUAGES } from "./code-languages"
import { Field, FieldLabel } from "@/components/ui/field"
import { Switch } from "@/components/ui/switch"
import { useTranslation } from "react-i18next"

type QuestionSettingsFieldsProps = {
    difficulty: QuestionDifficulty
    answerMode: AnswerMode
    answerModeDisclosed: boolean
    responseLanguage: CodeLanguage | null
    allowCodeExecution: boolean
    onDifficultyChange: (difficulty: QuestionDifficulty) => void
    onAnswerModeChange: (mode: AnswerMode) => void
    onAnswerModeDisclosedChange: (disclosed: boolean) => void
    onResponseLanguageChange: (language: CodeLanguage | null) => void
    onAllowCodeExecutionChange: (allowed: boolean) => void
}

export function QuestionSettingsFields({
    difficulty,
    answerMode,
    answerModeDisclosed,
    responseLanguage,
    allowCodeExecution,
    onDifficultyChange,
    onAnswerModeChange,
    onAnswerModeDisclosedChange,
    onResponseLanguageChange,
    onAllowCodeExecutionChange,
}: QuestionSettingsFieldsProps) {
    const { t } = useTranslation()

    return (
        <>
            <div className="grid gap-4 sm:grid-cols-2">
                <Field>
                    <FieldLabel htmlFor="question-difficulty">
                        {t("difficulty")}
                    </FieldLabel>
                    <select
                        id="question-difficulty"
                        className={NATIVE_SELECT_CLASS_NAME}
                        value={difficulty}
                        onChange={(event) =>
                            onDifficultyChange(
                                event.target.value as QuestionDifficulty
                            )
                        }
                    >
                        <option value="easy">{t("difficulty-easy")}</option>
                        <option value="medium">{t("difficulty-medium")}</option>
                        <option value="hard">{t("difficulty-hard")}</option>
                    </select>
                </Field>
                <Field>
                    <FieldLabel htmlFor="question-answer-mode">
                        {t("answer-mode")}
                    </FieldLabel>
                    <select
                        id="question-answer-mode"
                        className={NATIVE_SELECT_CLASS_NAME}
                        value={answerMode}
                        onChange={(event) =>
                            onAnswerModeChange(event.target.value as AnswerMode)
                        }
                    >
                        <option value="single">{t("single-choice")}</option>
                        <option value="multiple">{t("multiple-choice")}</option>
                        <option value="written">{t("written-answer")}</option>
                    </select>
                </Field>
            </div>
            {answerMode !== "written" && (
                <label className="flex cursor-pointer items-center justify-between gap-4 rounded-lg border p-4 text-sm">
                    <span>{t("disclose-answer-mode")}</span>
                    <Switch
                        checked={answerModeDisclosed}
                        onCheckedChange={onAnswerModeDisclosedChange}
                        aria-label={t("disclose-answer-mode")}
                    />
                </label>
            )}
            {answerMode === "written" && (
                <Field className="gap-3">
                    <FieldLabel htmlFor="written-response-language">
                        {t("written-response-format")}
                    </FieldLabel>
                    <select
                        id="written-response-language"
                        className={NATIVE_SELECT_CLASS_NAME}
                        value={responseLanguage ?? ""}
                        onChange={(event) =>
                            onResponseLanguageChange(
                                (event.target.value ||
                                    null) as CodeLanguage | null
                            )
                        }
                    >
                        <option value="">{t("plain-text")}</option>
                        {CODE_LANGUAGES.map((language) => (
                            <option key={language.value} value={language.value}>
                                {language.label}
                            </option>
                        ))}
                    </select>
                    {responseLanguage === "python" && (
                        <label className="flex cursor-pointer items-center justify-between gap-4 rounded-lg border p-4 text-sm">
                            <span>
                                <span className="block font-medium">
                                    {t("allow-code-execution")}
                                </span>
                                <span className="text-xs text-muted-foreground">
                                    {t("allow-code-execution-help")}
                                </span>
                            </span>
                            <Switch
                                checked={allowCodeExecution}
                                onCheckedChange={onAllowCodeExecutionChange}
                                aria-label={t("allow-code-execution")}
                            />
                        </label>
                    )}
                </Field>
            )}
        </>
    )
}

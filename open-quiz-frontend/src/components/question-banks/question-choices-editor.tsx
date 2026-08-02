import type { AnswerMode, CodeLanguage } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Plus } from "lucide-react"
import { useTranslation } from "react-i18next"
import { QuestionChoiceEditor } from "./question-choice-editor"
import type { EditableChoice } from "./question-form-types"

type QuestionChoicesEditorProps = {
    choices: EditableChoice[]
    answerMode: AnswerMode
    responseLanguage: CodeLanguage | null
    onChoicesChange: (choices: EditableChoice[]) => void
    onCorrectChoiceChange: (index: number, checked: boolean) => void
    onRemoveChoice: (index: number) => void
}

export function QuestionChoicesEditor({
    choices,
    answerMode,
    responseLanguage,
    onChoicesChange,
    onCorrectChoiceChange,
    onRemoveChoice,
}: QuestionChoicesEditorProps) {
    const { t } = useTranslation()

    function updateChoice(index: number, update: Partial<EditableChoice>) {
        onChoicesChange(
            choices.map((choice, choiceIndex) =>
                choiceIndex === index ? { ...choice, ...update } : choice
            )
        )
    }

    function addChoice() {
        onChoicesChange([
            ...choices,
            {
                label: "",
                is_correct: false,
                has_image: false,
                remove_image: false,
                hasCode: false,
                codeLanguage: "javascript",
                codeContent: "",
            },
        ])
    }

    return (
        <Field>
            <FieldLabel>
                {t(
                    answerMode === "written"
                        ? "expected-written-answer"
                        : "answer-choices"
                )}
            </FieldLabel>
            <div className="space-y-2">
                {choices.map((choice, index) =>
                    answerMode === "written" && index > 0 ? null : (
                        <QuestionChoiceEditor
                            key={choice.id ?? index}
                            choice={choice}
                            index={index}
                            choiceCount={choices.length}
                            answerMode={answerMode}
                            responseLanguage={responseLanguage}
                            onUpdate={(update) => updateChoice(index, update)}
                            onCorrectChange={(checked) =>
                                onCorrectChoiceChange(index, checked)
                            }
                            onRemove={() => onRemoveChoice(index)}
                        />
                    )
                )}
            </div>
            {answerMode !== "written" && (
                <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    className="mt-2 w-fit"
                    disabled={choices.length >= 12}
                    onClick={addChoice}
                >
                    <Plus />
                    {t("add-choice")}
                </Button>
            )}
        </Field>
    )
}

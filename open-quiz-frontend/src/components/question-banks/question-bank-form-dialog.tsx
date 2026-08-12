import type { GradeLevel, QuestionBank } from "@/api/types"
import { GradeLevelSelect } from "@/components/grade-level-select"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import {
    Field,
    FieldError,
    FieldGroup,
    FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { LoaderCircle, Pencil, Plus } from "lucide-react"
import type { FormEvent, ReactNode } from "react"
import { useTranslation } from "react-i18next"

type QuestionBankFormDialogProps = {
    open: boolean
    editingBank: QuestionBank | null
    gradeLevels: GradeLevel[]
    gradeLevel: string
    title: string
    newGradeLevel: string
    isAddingGradeLevel: boolean
    isBusy: boolean
    error: string | null
    onGradeLevelChange: (value: string) => void
    onTitleChange: (value: string) => void
    onNewGradeLevelChange: (value: string) => void
    onAddingGradeLevelChange: (value: boolean) => void
    onDeleteGradeLevel: (level: GradeLevel) => Promise<void>
    onAddGradeLevel: () => void
    onClose: () => void
    onSubmit: (event: FormEvent<HTMLFormElement>) => void
    questionManagement?: ReactNode
}

export function QuestionBankFormDialog({
    open,
    editingBank,
    gradeLevels,
    gradeLevel,
    title,
    newGradeLevel,
    isAddingGradeLevel,
    isBusy,
    error,
    onGradeLevelChange,
    onTitleChange,
    onNewGradeLevelChange,
    onAddingGradeLevelChange,
    onDeleteGradeLevel,
    onAddGradeLevel,
    onClose,
    onSubmit,
    questionManagement,
}: QuestionBankFormDialogProps) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen && !isBusy) onClose()
            }}
            title={t(
                editingBank ? "edit-question-bank" : "create-question-bank"
            )}
            description={t("create-question-bank-help")}
            className={editingBank ? "max-w-6xl" : "max-w-2xl"}
        >
            <form onSubmit={onSubmit}>
                <FieldGroup className="gap-4">
                    <Field>
                        <FieldLabel htmlFor="question-bank-title">
                            {t("question-bank-title")}
                        </FieldLabel>
                        <Input
                            id="question-bank-title"
                            value={title}
                            onChange={(event) =>
                                onTitleChange(event.target.value)
                            }
                            maxLength={160}
                            placeholder={t("question-bank-title-placeholder")}
                            required
                        />
                    </Field>
                    <Field>
                        <FieldLabel htmlFor="question-bank-grade-level">
                            {t("grade-level")}
                        </FieldLabel>
                        <div className="flex gap-2">
                            <GradeLevelSelect
                                id="question-bank-grade-level"
                                value={gradeLevel}
                                levels={gradeLevels}
                                onChange={onGradeLevelChange}
                                onDelete={onDeleteGradeLevel}
                                disabled={isBusy}
                            />
                            <Button
                                type="button"
                                size="icon"
                                variant="outline"
                                aria-label={t("add-grade-level")}
                                onClick={() =>
                                    onAddingGradeLevelChange(
                                        !isAddingGradeLevel
                                    )
                                }
                            >
                                <Plus />
                            </Button>
                        </div>
                        {isAddingGradeLevel && (
                            <div className="mt-2 flex gap-2">
                                <Input
                                    value={newGradeLevel}
                                    onChange={(event) =>
                                        onNewGradeLevelChange(
                                            event.target.value
                                        )
                                    }
                                    onKeyDown={(event) => {
                                        if (event.key === "Enter") {
                                            event.preventDefault()
                                            onAddGradeLevel()
                                        }
                                    }}
                                    maxLength={80}
                                    placeholder={t("grade-level-placeholder")}
                                />
                                <Button
                                    type="button"
                                    size="sm"
                                    onClick={onAddGradeLevel}
                                >
                                    {t("save-grade-level")}
                                </Button>
                            </div>
                        )}
                    </Field>
                    {editingBank && questionManagement}
                    {error && <FieldError>{error}</FieldError>}
                    <div className="flex justify-end gap-2 border-t pt-4">
                        <Button
                            type="button"
                            variant="outline"
                            disabled={isBusy}
                            onClick={onClose}
                        >
                            {t("cancel")}
                        </Button>
                        <Button type="submit" disabled={isBusy}>
                            {isBusy ? (
                                <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                            ) : editingBank ? (
                                <Pencil />
                            ) : (
                                <Plus />
                            )}
                            {t(
                                isBusy
                                    ? editingBank
                                        ? "saving-question-bank"
                                        : "creating-question-bank"
                                    : editingBank
                                      ? "save-question-bank"
                                      : "create-question-bank-action"
                            )}
                        </Button>
                    </div>
                </FieldGroup>
            </form>
        </Dialog>
    )
}

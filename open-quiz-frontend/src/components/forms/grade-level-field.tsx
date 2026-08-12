import type { GradeLevel } from "@/api/types"
import { GradeLevelSelect } from "@/components/grade-level-select"
import { Button } from "@/components/ui/button"
import { Field, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Plus } from "lucide-react"
import { useTranslation } from "react-i18next"

type GradeLevelFieldProps = {
    id: string
    value: string
    levels: GradeLevel[]
    newValue: string
    isAdding: boolean
    disabled: boolean
    onChange: (value: string) => void
    onNewValueChange: (value: string) => void
    onAddingChange: (value: boolean) => void
    onDelete: (level: GradeLevel) => Promise<void>
    onAdd: () => void
}

export function GradeLevelField({
    id,
    value,
    levels,
    newValue,
    isAdding,
    disabled,
    onChange,
    onNewValueChange,
    onAddingChange,
    onDelete,
    onAdd,
}: GradeLevelFieldProps) {
    const { t } = useTranslation()

    return (
        <Field>
            <FieldLabel htmlFor={id}>{t("grade-level")}</FieldLabel>
            <div className="flex gap-2">
                <GradeLevelSelect
                    id={id}
                    value={value}
                    levels={levels}
                    onChange={onChange}
                    onDelete={onDelete}
                    disabled={disabled}
                />
                <Button
                    type="button"
                    size="icon"
                    variant="outline"
                    aria-label={t("add-grade-level")}
                    onClick={() => onAddingChange(!isAdding)}
                >
                    <Plus />
                </Button>
            </div>
            {isAdding && (
                <div className="mt-2 flex gap-2">
                    <Input
                        value={newValue}
                        onChange={(event) =>
                            onNewValueChange(event.target.value)
                        }
                        onKeyDown={(event) => {
                            if (event.key === "Enter") {
                                event.preventDefault()
                                onAdd()
                            }
                        }}
                        maxLength={80}
                        placeholder={t("grade-level-placeholder")}
                    />
                    <Button type="button" size="sm" onClick={onAdd}>
                        {t("save-grade-level")}
                    </Button>
                </div>
            )}
        </Field>
    )
}

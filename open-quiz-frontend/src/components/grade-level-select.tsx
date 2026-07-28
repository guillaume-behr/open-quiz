import type { GradeLevel } from "@/api/types"
import { Button } from "@/components/ui/button"
import { Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"

type GradeLevelSelectProps = {
    id: string
    value: string
    levels: GradeLevel[]
    onChange: (value: string) => void
    onDelete: (level: GradeLevel) => Promise<void>
    disabled?: boolean
}

export function GradeLevelSelect({
    id,
    value,
    levels,
    onChange,
    onDelete,
    disabled = false,
}: GradeLevelSelectProps) {
    const { t } = useTranslation()
    const selected = levels.find((level) => level.name === value)

    async function confirmDelete(): Promise<void> {
        if (
            !selected ||
            !window.confirm(
                t("delete-grade-level-confirmation", {
                    level: selected.name,
                })
            )
        ) {
            return
        }
        try {
            await onDelete(selected)
            onChange("")
        } catch {
            // The parent displays the contextual API error.
        }
    }

    return (
        <div className="flex min-w-0 flex-1 gap-2">
            <select
                id={id}
                value={value}
                onChange={(event) => onChange(event.target.value)}
                disabled={disabled}
                className="h-9 min-w-0 flex-1 rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                required
            >
                <option value="">{t("choose-grade-level")}</option>
                {levels.map((level) => (
                    <option key={level.id} value={level.name}>
                        {level.name}
                    </option>
                ))}
            </select>
            {selected && (
                <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => void confirmDelete()}
                    disabled={disabled}
                    aria-label={t("delete-grade-level", {
                        level: selected.name,
                    })}
                    title={t("delete-grade-level", {
                        level: selected.name,
                    })}
                >
                    <Trash2 />
                </Button>
            )}
        </div>
    )
}

import type { GradeLevel } from "@/api/types"
import { ApiError } from "@/api/client"
import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { Toast } from "@/components/ui/toast"
import { Trash2 } from "lucide-react"
import { useEffect, useState } from "react"
import { useTranslation } from "react-i18next"

type GradeLevelSelectProps = {
    id: string
    value: string
    levels: GradeLevel[]
    onChange: (value: string) => void
    onDelete: (level: GradeLevel) => Promise<void>
    disabled?: boolean
    required?: boolean
    placeholder?: string
}

export function GradeLevelSelect({
    id,
    value,
    levels,
    onChange,
    onDelete,
    disabled = false,
    required = true,
    placeholder,
}: GradeLevelSelectProps) {
    const { t } = useTranslation()
    const selected = levels.find((level) => level.name === value)
    const [deleteError, setDeleteError] = useState<string | null>(null)
    const [levelToDelete, setLevelToDelete] = useState<GradeLevel | null>(null)
    const [isDeleting, setIsDeleting] = useState(false)

    useEffect(() => {
        if (!deleteError) return
        const timeout = window.setTimeout(() => setDeleteError(null), 5000)
        return () => window.clearTimeout(timeout)
    }, [deleteError])

    async function confirmDelete(): Promise<void> {
        if (!levelToDelete) return
        setIsDeleting(true)
        try {
            await onDelete(levelToDelete)
            onChange("")
            setLevelToDelete(null)
        } catch (error) {
            setDeleteError(
                error instanceof ApiError && error.status === 409
                    ? t("grade-level-in-use-error")
                    : t("grade-level-delete-error")
            )
            setLevelToDelete(null)
        } finally {
            setIsDeleting(false)
        }
    }

    return (
        <div className="flex min-w-0 flex-1 gap-2">
            {deleteError && <Toast message={deleteError} variant="error" />}
            <select
                id={id}
                value={value}
                onChange={(event) => onChange(event.target.value)}
                disabled={disabled}
                className="h-9 min-w-0 flex-1 rounded-lg border border-input bg-background px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                required={required}
            >
                <option value="" disabled={required}>
                    {placeholder ?? t("choose-grade-level")}
                </option>
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
                    onClick={() => setLevelToDelete(selected)}
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
            <Dialog
                open={levelToDelete !== null}
                onOpenChange={(open) => {
                    if (!open && !isDeleting) setLevelToDelete(null)
                }}
                title={t("delete-grade-level", {
                    level: levelToDelete?.name ?? "",
                })}
                description={t("delete-grade-level-confirmation", {
                    level: levelToDelete?.name ?? "",
                })}
                size="sm"
            >
                <div className="flex justify-end gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        disabled={isDeleting}
                        onClick={() => setLevelToDelete(null)}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        type="button"
                        variant="destructive"
                        disabled={isDeleting}
                        onClick={() => void confirmDelete()}
                    >
                        {t("delete")}
                    </Button>
                </div>
            </Dialog>
        </div>
    )
}

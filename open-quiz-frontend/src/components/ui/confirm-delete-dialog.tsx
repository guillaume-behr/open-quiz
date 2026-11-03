import { Button } from "@/components/ui/button"
import { Dialog } from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field"
import { LoaderCircle, Trash2 } from "lucide-react"
import { useTranslation } from "react-i18next"

/**
 * Asks to confirm a deletion. It cannot be dismissed while the deletion
 * runs, and shows the error of a failed one above its buttons.
 */
export function ConfirmDeleteDialog({
    open,
    title,
    description,
    confirmLabel,
    isBusy,
    error = null,
    onClose,
    onConfirm,
}: {
    open: boolean
    title: string
    description: string
    /** The confirm button's label, "Delete" unless given. */
    confirmLabel?: string
    isBusy: boolean
    error?: string | null
    onClose: () => void
    onConfirm: () => void
}) {
    const { t } = useTranslation()
    return (
        <Dialog
            open={open}
            onOpenChange={(nextOpen) => {
                if (!nextOpen && !isBusy) onClose()
            }}
            title={title}
            description={description}
            size="sm"
        >
            <div className="space-y-4">
                {error && <FieldError>{error}</FieldError>}
                <div className="flex justify-end gap-2">
                    <Button
                        type="button"
                        variant="outline"
                        disabled={isBusy}
                        onClick={onClose}
                    >
                        {t("cancel")}
                    </Button>
                    <Button
                        type="button"
                        variant="destructive"
                        disabled={isBusy}
                        onClick={onConfirm}
                    >
                        {isBusy ? (
                            <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                        ) : (
                            <Trash2 />
                        )}
                        {confirmLabel ?? t("delete")}
                    </Button>
                </div>
            </div>
        </Dialog>
    )
}

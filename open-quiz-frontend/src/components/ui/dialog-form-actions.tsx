import { Button } from "@/components/ui/button"
import { LoaderCircle, Pencil, Plus } from "lucide-react"
import { useTranslation } from "react-i18next"

type DialogFormActionsProps = {
    isBusy: boolean
    isEditing: boolean
    submitLabel: string
    onClose: () => void
    submitDisabled?: boolean
    bordered?: boolean
    /** The id of the form to submit, when the actions sit outside it. */
    form?: string
}

export function DialogFormActions({
    isBusy,
    isEditing,
    submitLabel,
    onClose,
    submitDisabled = false,
    bordered = true,
    form,
}: DialogFormActionsProps) {
    const { t } = useTranslation()

    return (
        <div
            className={`flex justify-end gap-2 ${bordered ? "border-t pt-4" : ""}`}
        >
            <Button
                type="button"
                variant="outline"
                disabled={isBusy}
                onClick={onClose}
            >
                {t("cancel")}
            </Button>
            <Button
                type="submit"
                form={form}
                disabled={isBusy || submitDisabled}
            >
                {isBusy ? (
                    <LoaderCircle className="animate-spin motion-reduce:animate-none" />
                ) : isEditing ? (
                    <Pencil />
                ) : (
                    <Plus />
                )}
                {submitLabel}
            </Button>
        </div>
    )
}

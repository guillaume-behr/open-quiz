import { cn } from "@/lib/utils"
import { LoaderCircle } from "lucide-react"
import { useTranslation } from "react-i18next"

const ICON_SIZES = {
    6: "size-6",
    7: "size-7",
    8: "size-8",
    9: "size-9",
} as const

/**
 * A spinner announced as loading, centred in a box that `className` sizes
 * (by default, the height of a short list).
 */
export function LoadingState({
    className = "min-h-40",
    size = 7,
}: {
    className?: string
    size?: keyof typeof ICON_SIZES
}) {
    const { t } = useTranslation()
    return (
        <div
            className={cn("flex items-center justify-center", className)}
            role="status"
            aria-label={t("page-loading")}
        >
            <LoaderCircle
                className={cn(
                    ICON_SIZES[size],
                    "animate-spin text-primary motion-reduce:animate-none"
                )}
                aria-hidden="true"
            />
        </div>
    )
}

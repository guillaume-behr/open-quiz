import { Button } from "@/components/ui/button"
import { LoaderCircle, RotateCcw } from "lucide-react"
import type { ReactNode } from "react"
import { useTranslation } from "react-i18next"

/**
 * Shows a list's loading state, or its load error with a way to retry,
 * before its content: an unloaded list must not read as an empty one.
 */
export function ListStatus({
    isLoading,
    error,
    onRetry,
    children,
}: {
    /** True until the list has loaded once. */
    isLoading: boolean
    /** The message of the last failed load, if it failed. */
    error: string | null
    onRetry: () => void
    children: ReactNode
}) {
    const { t } = useTranslation()
    if (isLoading) {
        return (
            <div
                className="flex min-h-40 items-center justify-center"
                role="status"
                aria-label={t("page-loading")}
            >
                <LoaderCircle
                    className="size-7 animate-spin text-primary motion-reduce:animate-none"
                    aria-hidden="true"
                />
            </div>
        )
    }
    if (error) return <LoadErrorNotice message={error} onRetry={onRetry} />
    return children
}

/** Says that something failed to load, with a button to load it again. */
export function LoadErrorNotice({
    message,
    onRetry,
}: {
    message: string
    onRetry: () => void
}) {
    const { t } = useTranslation()
    return (
        <div
            role="alert"
            className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm text-destructive"
        >
            <p>{message}</p>
            <Button type="button" variant="outline" onClick={onRetry}>
                <RotateCcw aria-hidden="true" />
                {t("retry")}
            </Button>
        </div>
    )
}

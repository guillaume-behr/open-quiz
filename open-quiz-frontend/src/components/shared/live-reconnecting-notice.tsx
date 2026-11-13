import { LoaderCircle } from "lucide-react"
import { useTranslation } from "react-i18next"

/**
 * Says that live updates stopped and are being restored, so a view that has
 * gone stale does not pass for a current one. The status region is always
 * rendered so screen readers announce the change.
 */
export function LiveReconnectingNotice({
    reconnecting,
}: {
    reconnecting: boolean
}) {
    const { t } = useTranslation()
    return (
        <p
            role="status"
            className="flex items-center justify-center gap-2 text-sm text-muted-foreground empty:hidden"
        >
            {reconnecting && (
                <>
                    <LoaderCircle
                        aria-hidden="true"
                        className="size-4 animate-spin motion-reduce:animate-none"
                    />
                    {t("live-reconnecting")}
                </>
            )}
        </p>
    )
}

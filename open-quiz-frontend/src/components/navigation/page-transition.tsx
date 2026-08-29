import { LoaderCircle } from "lucide-react"
import { useEffect, useState, type ReactNode } from "react"
import { useTranslation } from "react-i18next"
import { useLocation } from "react-router"

const MINIMUM_TRANSITION_DURATION_MS = 200

export function PageTransition({ children }: { children: ReactNode }) {
    const { t } = useTranslation()
    const location = useLocation()
    const [displayedLocationKey, setDisplayedLocationKey] = useState(
        location.key
    )
    const isTransitioning = displayedLocationKey !== location.key

    useEffect(() => {
        if (!isTransitioning) return

        const timeout = window.setTimeout(() => {
            setDisplayedLocationKey(location.key)
        }, MINIMUM_TRANSITION_DURATION_MS)

        return () => window.clearTimeout(timeout)
    }, [isTransitioning, location.key])

    return (
        <div
            className="relative flex min-h-0 w-full flex-1"
            aria-busy={isTransitioning}
        >
            {children}
            {isTransitioning && (
                <div
                    className="absolute inset-0 z-40 flex items-center justify-center bg-background"
                    role="status"
                    aria-label={t("page-loading")}
                >
                    <LoaderCircle
                        className="size-9 animate-spin text-primary motion-reduce:animate-none"
                        aria-hidden="true"
                    />
                </div>
            )}
        </div>
    )
}

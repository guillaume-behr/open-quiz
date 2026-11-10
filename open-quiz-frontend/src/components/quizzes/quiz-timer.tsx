import { Clock3 } from "lucide-react"
import { useEffect, useRef, useState } from "react"
import { useTranslation } from "react-i18next"
import { cn } from "@/lib/utils"
import {
    crossedAnnouncement,
    secondsLeft,
    serverClockAnchor,
} from "@/lib/server-clock"

// Minutes left at which a screen reader hears how much time remains.
/**
 * Counts down to `endsAt` on the server's clock.
 *
 * `serverNow` is the server's time when the state was built. The timer
 * anchors it to the monotonic `performance.now()` on receipt, so a client
 * clock that is off, or changed during the exam, does not move the time
 * left. Without it, the timer falls back to the client clock.
 */
export function QuizTimer({
    endsAt,
    serverNow = null,
    variant = "default",
}: {
    endsAt: string | null
    serverNow?: string | null
    variant?: "default" | "display"
}) {
    const { t } = useTranslation()
    const [anchor, setAnchor] = useState(() => serverClockAnchor(serverNow))
    const [anchoredServerNow, setAnchoredServerNow] = useState(serverNow)
    if (anchoredServerNow !== serverNow) {
        setAnchoredServerNow(serverNow)
        setAnchor(serverClockAnchor(serverNow))
    }
    const [remaining, setRemaining] = useState(() =>
        endsAt ? secondsLeft(endsAt, anchor) : 0
    )
    const [announcement, setAnnouncement] = useState("")
    const previousRemaining = useRef<number | null>(null)

    useEffect(() => {
        if (!endsAt) return
        const update = () => {
            const seconds = secondsLeft(endsAt, anchor)
            const previous = previousRemaining.current
            previousRemaining.current = seconds
            setRemaining(seconds)
            const crossed = crossedAnnouncement(previous, seconds)
            if (crossed !== undefined)
                setAnnouncement(t("timer-minutes-left", { count: crossed }))
        }
        update()
        const interval = window.setInterval(update, 1000)
        return () => window.clearInterval(interval)
    }, [anchor, endsAt, t])

    if (!endsAt) return null
    const isDisplay = variant === "display"
    return (
        <div
            className={cn(
                "inline-flex items-center gap-2 rounded-full border bg-background px-4 py-2 font-mono font-bold tabular-nums transition-colors",
                isDisplay &&
                    "gap-[0.25em] px-[0.35em] py-[0.1em] text-[clamp(3.5rem,17vw,15rem)] leading-none",
                remaining <= 60 &&
                    "border-destructive/40 bg-destructive/10 text-destructive"
            )}
            role="timer"
        >
            <Clock3 className={isDisplay ? "size-[0.7em]" : "size-4"} />
            {Math.floor(remaining / 60)}:
            {(remaining % 60).toString().padStart(2, "0")}
            <span className="sr-only" aria-live="assertive">
                {announcement}
            </span>
        </div>
    )
}

import { Clock3 } from "lucide-react"
import { useEffect, useState } from "react"
import { cn } from "@/lib/utils"

export function QuizTimer({
    endsAt,
    variant = "default",
}: {
    endsAt: string | null
    variant?: "default" | "display"
}) {
    const [remaining, setRemaining] = useState(0)

    useEffect(() => {
        if (!endsAt) return
        const update = () =>
            setRemaining(
                Math.max(
                    0,
                    Math.floor((new Date(endsAt).getTime() - Date.now()) / 1000)
                )
            )
        update()
        const interval = window.setInterval(update, 1000)
        return () => window.clearInterval(interval)
    }, [endsAt])

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
        </div>
    )
}

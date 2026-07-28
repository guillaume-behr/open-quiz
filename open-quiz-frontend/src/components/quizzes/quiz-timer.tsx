import { Clock3 } from "lucide-react"
import { useEffect, useState } from "react"

export function QuizTimer({ endsAt }: { endsAt: string | null }) {
    const [remaining, setRemaining] = useState(0)

    useEffect(() => {
        if (!endsAt) return
        const update = () =>
            setRemaining(
                Math.max(
                    0,
                    Math.ceil((new Date(endsAt).getTime() - Date.now()) / 1000)
                )
            )
        update()
        const interval = window.setInterval(update, 1000)
        return () => window.clearInterval(interval)
    }, [endsAt])

    if (!endsAt) return null
    return (
        <div
            className="inline-flex items-center gap-2 rounded-full border bg-background px-4 py-2 font-mono font-bold"
            role="timer"
        >
            <Clock3 className="size-4" />
            {Math.floor(remaining / 60)}:
            {(remaining % 60).toString().padStart(2, "0")}
        </div>
    )
}
